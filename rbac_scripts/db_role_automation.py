import snowflake.connector
import json
import re
import sys
import logging
import os
def get_current_grants(cursor, obj_type, obj_name, grantee_name, database_name, schema_name=None):
    query = f"""
        SELECT PRIVILEGE_TYPE, GRANTEE
        FROM {database_name}.INFORMATION_SCHEMA.OBJECT_PRIVILEGES
        WHERE GRANTEE='{grantee_name}' AND OBJECT_TYPE='{obj_type}' AND OBJECT_NAME='{obj_name}'
    """
    if schema_name:
        query += f" AND OBJECT_SCHEMA='{schema_name}'"
    
    cursor.execute(query)
    return [{"privilege": row[0], "grantee": row[1]} for row in cursor.fetchall()]

def restore_previous_grants(cursor, obj_type, obj_name, previous_grants, grantee_type, grantee_name, database_name, schema_name=None):
   
    msg = []
    for grant in previous_grants:
        privilege, grantee = grant["privilege"], grant["grantee"]
        if obj_type == "DATABASE":
            query = f"GRANT {privilege} ON {obj_type} {obj_name} TO {grantee_type} {database_name}.{grantee}"
        elif obj_type == "SCHEMA":
            query = f"GRANT {privilege} ON {obj_type} {database_name}.{obj_name} TO {grantee_type} {database_name}.{grantee}"
        else:
            query = f"GRANT {privilege} ON {obj_type} {database_name}.{schema_name}.{obj_name} TO {grantee_type} {database_name}.{grantee}"
        cursor.execute(query)
        msg.append(f"RESTORE: {query}")
    return msg
        


def revoke_and_grant(cursor, obj_type, obj_name, database_name, schema_name, privileges, grantee_type, grantee_name):
    """
    Revoke existing grants and apply new grants. If new grants fail, restore previous grants.
    """
    msg = []
    previous_grants = get_current_grants(cursor, obj_type, obj_name, grantee_name, database_name, schema_name)
    try:
        sql_statement = f"REVOKE ALL PRIVILEGES ON {obj_type} {database_name}.{schema_name}.{obj_name} FROM {grantee_type} {database_name}.{grantee_name}"
        cursor.execute(sql_statement)
        msg.append(f"SUCCESS: {sql_statement}")
        
        sql_statement = f"GRANT {', '.join(privileges).upper()} ON {obj_type} {database_name}.{schema_name}.{obj_name} TO {grantee_type} {database_name}.{grantee_name}"
        cursor.execute(sql_statement)
        msg.append(f"SUCCESS: {sql_statement}")

    except Exception as e:
        print(f"ERROR OCCURED FOR {obj_type} with name {obj_name}, error message: {e}")
        msg.append(f"FAILED: FOR {obj_type} with name {obj_name} - Error: {str(e)}")
        ms = restore_previous_grants(cursor, obj_type, obj_name, previous_grants, grantee_type, grantee_name, database_name, schema_name)
        msg += ms
    return msg


def replace_placeholders(json_data, variables):
    """
    Replaces placeholders like ${VAR_NAME} in the json_data with corresponding values from the variables dictionary.
    """
    
    json_str = json.dumps(json_data)
    pattern = re.compile(r"\$\{(\w+)\}")
    def replacer(match):
        variable_name = match.group(1)
        return variables.get(variable_name, match.group(0))
    updated_json_str = pattern.sub(replacer, json_str)
    updated_json_data = json.loads(updated_json_str)
    return updated_json_data



def grant_permissions_from_json(connection, json_data):
    

    cursor = connection.cursor()
    messages = []

    try:
        for role_obj in json_data["role"]:
            
            grantee_type = role_obj["grantee_type"]
            grantee_name = role_obj["grantee_name"]
            enforcement_action = role_obj["enforcement_action"]
            database_name = role_obj["database_name"]
            
            # if role doesn't exist: create using SYSADMIN
            roles = cursor.execute(f"SHOW DATABASE ROLES IN {database_name}").fetchall()
            role_exists = any(row[1] == grantee_name for row in roles)
            if not role_exists:
                cursor.execute("USE ROLE SYSADMIN")
                create_query = f"CREATE {grantee_type} {database_name}.{grantee_name}"
                cursor.execute(create_query)
                print(f"{grantee_name}  role created...")

            cursor.execute("USE ROLE SECURITYADMIN")
            
            # ITERATE THROUGH EACH GRANT
            for grantee in role_obj["grantees"]:
                obj_type = grantee["type"].upper()
                privileges = grantee["privileges"]
                obj_name = grantee["name"]
                
                # CONDITITON FOR ENFORCE THE PRIVILEGES
                if enforcement_action == "ENFORCE":
                
                    if obj_type == "DATABASE":
                            
                        previous_grants = get_current_grants(cursor, obj_type, obj_name, grantee_type, grantee_name, database_name)
                        try: 
                            cursor.execute(f"REVOKE ALL PRIVILEGES ON DATABASE {obj_name} FROM {grantee_type} {database_name}.{grantee_name}")
                            for privilege in privileges:
                                if 'FUTURE' in privilege:
                                    privilege_parts = privilege.split(' - ')
                                    privilege_name = privilege_parts[0]
                                    privilege_type = privilege_parts[1]

                                    sql_statement = f"GRANT {privilege_name} ON {privilege_type}S IN {obj_type} {database_name} TO {grantee_type} {database_name}.{grantee_name}"
                                    cursor.execute(sql_statement)
                                    messages.append(f"SUCCESS: {sql_statement}")

                                else:
                                    cursor.execute(f"GRANT {privilege.upper()} ON DATABASE {obj_name} TO {grantee_type} {database_name}.{grantee_name}")
                        except Exception as e:
                            
                            print(f"ERROR OCCURED FOR {obj_type} with name {obj_name}, error message: {str(e)}")
                            messages.append(f"FAILED: FOR {obj_type} with name {obj_name} - Error: {str(e)}")
                            msg = restore_previous_grants(cursor, obj_type, obj_name, previous_grants, grantee_type, grantee_name, database_name)
                            
                            messages+=msg

                    elif obj_type == "SCHEMA":
                    
                        if "all" in obj_name:
                            obj_types = obj_type.upper() + 'S'
                            cursor.execute(f"SHOW {obj_types} IN DATABASE {database_name}")
                            object_names = [row[1] for row in cursor.fetchall()]
                            for objname in object_names:
                                if objname not in ["INFORMATION_SCHEMA", "PUBLIC"]:
                                    previous_grants = get_current_grants(cursor, obj_type, objname, grantee_type, grantee_name, database_name)
                                    try:
                                        cursor.execute(f"REVOKE ALL PRIVILEGES ON SCHEMA {database_name}.{objname} FROM {grantee_type} {database_name}.{grantee_name}")
                                        for privilege in privileges:
                                            if 'FUTURE' in privilege:
                                                privilege_parts = privilege.split(' - ')
                                                privilege_name = privilege_parts[0]
                                                privilege_type = privilege_parts[1]

                                                sql_statement = f"GRANT {privilege_name} ON {privilege_type}S IN {obj_type} {database_name}.{objname} TO {grantee_type} {database_name}.{grantee_name}"
                                                cursor.execute(sql_statement)
                                                messages.append(f"SUCCESS: {sql_statement}")
                                            else:
                                                sql_statement = f"GRANT {privilege.upper()} ON SCHEMA {database_name}.{objname} TO {grantee_type} {database_name}.{grantee_name}"
                                                cursor.execute(sql_statement)
                                                messages.append(f"SUCCESS: {sql_statement}")
                                                
                                    except Exception as e:
                                        print(f"ERROR OCCURED FOR {obj_type} with name {obj_name}, error message: {str(e)}")
                                        messages.append(f"FAILED: FOR {obj_type} with name {obj_name} - Error: {str(e)}")
                                        msg = restore_previous_grants(cursor, obj_type, objname, previous_grants, grantee_type, grantee_name, database_name=database_name)
                                        messages+=msg
                                

                        else:

                            for schema in obj_name:
                                previous_grants = get_current_grants(cursor, obj_type, schema, grantee_type, grantee_name, database_name)
                                try:
                                    cursor.execute(f"REVOKE ALL PRIVILEGES ON SCHEMA {database_name}.{schema} FROM {grantee_type} {database_name}.{grantee_name}")
                                    for privilege in privileges:
                                        if 'FUTURE' in privilege:
                                            privilege_parts = privilege.split(' - ')
                                            privilege_name = privilege_parts[0]
                                            privilege_type = privilege_parts[1]

                                            sql_statement = f"GRANT {privilege_name} ON {privilege_type}S IN {obj_type} {database_name}.{schema} TO {grantee_type} {database_name}.{grantee_name}"
                                            cursor.execute(sql_statement)
                                            messages.append(f"SUCCESS: {sql_statement}")
                                        else:
                                            sql_statement = f"GRANT {privilege.upper()} ON SCHEMA {database_name}.{schema} TO {grantee_type} {database_name}.{grantee_name}"
                                            cursor.execute(sql_statement)
                                            messages.append(f"SUCCESS: {sql_statement}")
                                except Exception as e:
                                    print(f"ERROR OCCURED FOR {obj_type} with name {obj_name}, error message: {str(e)}")
                                    messages.append(f"FAILED: FOR {obj_type} with name {obj_name} - Error: {str(e)}")
                                    msg = restore_previous_grants(cursor, obj_type, schema, previous_grants, grantee_type, grantee_name, database_name=database_name)
                                    messages+=msg

                    else:
                        if "all" in grantee["schema_name"]:
                            cursor.execute(f"SHOW SCHEMAS IN DATABASE {database_name}")
                            schema_names = [row[1] for row in cursor.fetchall()]


                            for schema_name in schema_names:

                                if schema_name not in ["INFORMATION_SCHEMA", "PUBLIC"]:
                            
                                    if "all" in obj_name:
                                        obj_types = obj_type.upper() + 'S'
                                        cursor.execute(f"SHOW {obj_types} IN SCHEMA {database_name}.{schema_name}")
                                        object_names = [row[1] for row in cursor.fetchall()]
                                        for objname in object_names:
                                            revoke_and_grant(cursor, obj_type, objname, database_name, schema_name, privileges, grantee_type, grantee_name)
                                    else:
                                        for object_name in obj_name:
                                            revoke_and_grant(cursor, obj_type, object_name, database_name, schema_name, privileges, grantee_type, grantee_name)

                            
                        else:
                            for schema_name in grantee["schema_name"]:
                                if schema_name not in ["INFORMATION_SCHEMA", "PUBLIC"]:
                                    if "all" in obj_name:
                                        obj_types = obj_type.upper() + 'S'
                                        cursor.execute(f"SHOW {obj_types} IN SCHEMA {database_name}.{schema_name}")
                                        object_names = [row[1] for row in cursor.fetchall()]
                                        for objname in object_names:
                                            revoke_and_grant(cursor, obj_type, objname, database_name, schema_name, privileges, grantee_type, grantee_name)
                                    else:
                                        for object_name in obj_name:
                                            revoke_and_grant(cursor, obj_type, object_name, database_name, schema_name, privileges, grantee_type, grantee_name)
                            
                # CONDITION FOR MERGING THE PRIVILEGES
                elif enforcement_action == "MERGE":
                        if obj_type == "DATABASE":
                            for privilege in privileges:
                                if 'FUTURE' in privilege:
                                    privilege_parts = privilege.split(' - ')
                                    privilege_name = privilege_parts[0]
                                    privilege_type = privilege_parts[1]

                                    sql_statement = f"GRANT {privilege_name} ON {privilege_type}S IN {obj_type} {database_name} TO {grantee_type} {database_name}.{grantee_name}"
                                    cursor.execute(sql_statement)
                                    messages.append(f"SUCCESS: {sql_statement}")

                                else:
                                    sql_statement = f"GRANT {privilege.upper()} ON DATABASE {obj_name} TO {grantee_type} {database_name}.{grantee_name}"
                                    cursor.execute(sql_statement)
                                    messages.append(f"SUCCESS: {sql_statement}")

                        elif obj_type == "SCHEMA":
                            if "all" in obj_name:
                                obj_types = obj_type.upper() + 'S'
                                cursor.execute(f"SHOW {obj_types} IN DATABASE {database_name}")
                                object_names = [row[1] for row in cursor.fetchall()]
                                    # Apply the new grants
                                for objname in object_names:
                                    if objname not in ["INFORMATION_SCHEMA", "PUBLIC"]:
                                        for privilege in privileges:
                                            if 'FUTURE' in privilege:
                                                privilege_parts = privilege.split(' - ')
                                                privilege_name = privilege_parts[0]
                                                privilege_type = privilege_parts[1]

                                                sql_statement = f"GRANT {privilege_name} ON {privilege_type}S IN {obj_type} {database_name}.{objname} TO {grantee_type} {database_name}.{grantee_name}"
                                                cursor.execute(sql_statement)
                                                messages.append(f"SUCCESS: {sql_statement}")

                                            else:
                                                sql_statement = f"GRANT {privilege.upper()} ON SCHEMA {database_name}.{objname} TO {grantee_type} {database_name}.{grantee_name}"
                                                cursor.execute(sql_statement)
                                                messages.append(f"SUCCESS: {sql_statement}")
                            else:
                                for schema in obj_name:
                                    for privilege in privileges:
                                        if 'FUTURE' in privilege:
                                            privilege_parts = privilege.split(' - ')
                                            privilege_name = privilege_parts[0]
                                            privilege_type = privilege_parts[1]

                                            sql_statement = f"GRANT {privilege_name} ON {privilege_type}S IN {obj_type} {database_name}.{schema} TO {grantee_type} {database_name}.{grantee_name}"
                                            cursor.execute(sql_statement)
                                            messages.append(f"SUCCESS: {sql_statement}")
                                        else:
                                            sql_statement = f"GRANT {privilege.upper()} ON SCHEMA {database_name}.{schema} TO {grantee_type} {database_name}.{grantee_name}"
                                            cursor.execute(sql_statement)
                                            messages.append(f"SUCCESS: {sql_statement}")
                        
                        else:
                            if "all" in grantee["schema_name"]:
                                cursor.execute(f"SHOW SCHEMAS IN DATABASE {database_name}")
                                schema_names = [row[1] for row in cursor.fetchall()]


                                for schema_name in schema_names:

                                    if schema_name not in ["INFORMATION_SCHEMA", "PUBLIC"]:
                                
                                        if "all" in obj_name:
                                            obj_types = obj_type.upper() + 'S'
                                            cursor.execute(f"SHOW {obj_types} IN SCHEMA {database_name}.{schema_name}")
                                            columns = [desc[0] for desc in cursor.description]
                                            name_idx = columns.index("name")

                                            object_names = [row[name_idx] for row in cursor.fetchall()]
                                            for objname in object_names:
                                                sql_statement = f"GRANT {', '.join(privileges).upper()}  ON {obj_type} {database_name}.{schema_name}.{objname} TO {grantee_type} {database_name}.{grantee_name}"
                                                cursor.execute(sql_statement)
                                                messages.append(f"SUCCESS: {sql_statement}")
                                        else:
                                            for object_name in obj_name:
                                                sql_statement = f"GRANT {', '.join(privileges).upper()} ON {obj_type} {database_name}.{schema_name}.{object_name} TO {grantee_type} {database_name}.{grantee_name}"
                                                cursor.execute(sql_statement)
                                                messages.append(f"SUCCESS: {sql_statement}")

                                
                            else:
                                for schema_name in grantee["schema_name"]:
                                    if "all" in obj_name:
                                        obj_types = obj_type.upper() + 'S'
                                        cursor.execute(f"SHOW {obj_types} IN SCHEMA {database_name}.{schema_name}")
                                        columns = [desc[0] for desc in cursor.description]
                                        name_idx = columns.index("name")

                                        object_names = [row[name_idx] for row in cursor.fetchall()]
                                        for objname in object_names:
                                            sql_statement = f"GRANT {', '.join(privileges).upper()}  ON {obj_type} {database_name}.{schema_name}.{objname} TO {grantee_type} {database_name}.{grantee_name}"
                                            cursor.execute(sql_statement)
                                            messages.append(f"SUCCESS: {sql_statement}")
                                    else:
                                        for object_name in obj_name:
                                            sql_statement = f"GRANT {', '.join(privileges).upper()}  ON {obj_type} {database_name}.{schema_name}.{object_name} TO {grantee_type} {database_name}.{grantee_name}"
                                            cursor.execute(sql_statement)
                                            messages.append(f"SUCCESS: {sql_statement}")
                            
    finally:
        cursor.close()
    
    return messages


if __name__ == "__main__":
    
    connection = snowflake.connector.connect(
        user=os.getenv('SNOWFLAKE_USERNAME'),
        password=os.getenv('SNOWFLAKE_PASSWORD'),
        account=os.getenv('SNOWFLAKE_ACCOUNT'),
        role=os.getenv('SNOWFLAKE_ROLE'),
        warehouse='COMPUTE_WH',
        database='SNOWFLAKE',
        schema='INFORMATION_SCHEMA'
    )
    
    variables = os.getenv('VARIABLES', 'False')
    
    if variables.lower() != 'false':
        try:
            variables = json.loads(variables)
        except json.JSONDecodeError:
            print("Invalid JSON in VARIABLES. Exiting.")
            exit(1)
        
        template_json_file_path = "db_role_grants_config_files/sample_json_file.json"
        with open(template_json_file_path, 'r') as f:
            json_data = json.load(f)
            
        # variables = [{"DB_NAME": "MANI_DB"}]
        # REPLACING PLACE HOLDERS IN JSON IF ANY
        for var in variables:
            json_data = replace_placeholders(json_data, variables)
            messages = grant_permissions_from_json(connection, json_data)
            print('\n'.join(messages))
    else:
        added_files = os.getenv('ADDED_FILES')
        json_array = json.loads(added_files)

        for file in json_array:
            print(file)
            with open(file, 'r') as f:
                json_data = json.load(f)
                
            print(json_data)

            messages = grant_permissions_from_json(connection, json_data)
            print('\n'.join(messages))
    connection.close()

