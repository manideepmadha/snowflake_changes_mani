import snowflake.connector
import json
import sys

def get_current_grants(cursor, obj_type, obj_name, grantee_type, grantee_name, database_name, schema_name=None):
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
    for grant in previous_grants:
        privilege, grantee = grant["privilege"], grant["grantee"]
        if obj_type == "DATABASE":
            query = f"GRANT {privilege} ON {obj_type} {obj_name} TO {grantee_type} {database_name}.{grantee}"
        elif obj_type == "SCHEMA":
            query = f"GRANT {privilege} ON {obj_type} {database_name}.{obj_name} TO {grantee_type} {database_name}.{grantee}"
        else:
            query = f"GRANT {privilege} ON {obj_type} {database_name}.{schema_name}.{obj_name} TO {grantee_type} {database_name}.{grantee}"
        cursor.execute(query)


def revoke_and_grant(cursor, obj_type, obj_name, database_name, schema_name, privileges, grantee_type, grantee_name):
    """
    Revoke existing grants and apply new grants. If new grants fail, restore previous grants.
    """
    previous_grants = get_current_grants(cursor, obj_type, obj_name, grantee_type, grantee_name, database_name, schema_name)
    
    try:
        cursor.execute(f"REVOKE ALL PRIVILEGES ON {obj_type} {database_name}.{schema_name}.{obj_name} FROM {grantee_type} {database_name}.{grantee_name}")
        cursor.execute(f"GRANT {', '.join(privileges).upper()} ON {obj_type} {database_name}.{schema_name}.{obj_name} TO {grantee_type} {database_name}.{grantee_name}")

    except Exception as e:
        # Restore previous grants if any failure occurs
        restore_previous_grants(cursor, obj_type, obj_name, previous_grants, grantee_type, grantee_name, database_name, schema_name)

def grant_permissions_from_json(connection, json_file):
    with open(json_file, 'r') as f:
        json_data = json.load(f)
        
    cursor = connection.cursor()
    # json_data = json.loads(cursor.execute(f"SELECT $1 FROM @my_stage/db_role_config.json").fetchone()[0])
    # print(json_data)

    try:
        for role_obj in json_data["role"]:
            
            grantee_type = role_obj["grantee_type"]
            grantee_name = role_obj["grantee_name"]
            enforcement_action = role_obj["enforcement_action"]
            database_name = role_obj["database_name"]
            

            cursor.execute(f"USE ROLE SYSADMIN")
            roles = cursor.execute(f"SHOW DATABASE ROLES IN {database_name}").fetchall()
            role_exists = any(row[1] == grantee_name for row in roles)
            if not role_exists:
                create_query = f"CREATE {grantee_type} {database_name}.{grantee_name}"
                cursor.execute(create_query)
                print(f"{grantee_name}  role created...")
                

            # Loop through each grantee (objects) for the role
            for grantee in role_obj["grantees"]:
                obj_type = grantee["type"].upper()
                privileges = grantee["privileges"]
                obj_name = grantee["name"]
                
                if obj_type == "DATABASE":
                    
                    if enforcement_action == "ENFORCE":
                        
                        previous_grants = get_current_grants(cursor, obj_type, obj_name, grantee_type, grantee_name, database_name)
                        try: 
                            cursor.execute(f"REVOKE ALL PRIVILEGES ON DATABASE {obj_name} FROM {grantee_type} {database_name}.{grantee_name}")
                            for privilege in privileges:
                                if 'FUTURE' in privilege:
                                    privilege_parts = privilege.split(' - ')
                                    privilege_name = privilege_parts[0]
                                    privilege_type = privilege_parts[1]

                                    cursor.execute(f"GRANT {privilege_name} ON {privilege_type}S IN {obj_type} {database_name} TO {grantee_type} {database_name}.{grantee_name}")

                                else:
                                    cursor.execute(f"GRANT {privilege.upper()} ON DATABASE {obj_name} TO {grantee_type} {database_name}.{grantee_name}")
                            #grant usage on future schemas in database DEV_TZ to database role DEV_TZ.DEV_TZ_READ_ONLY;
                        except Exception as e:
                            # Restore previous grants if any failure occurs
                            restore_previous_grants(cursor, obj_type, obj_name, previous_grants, grantee_type, grantee_name, database_name)
                    elif enforcement_action == "MERGE":
                        # Apply the new grants
                        cursor.execute(f"GRANT {', '.join(privileges).upper()} ON DATABASE {database_name} TO {grantee_type} {database_name}.{grantee_name}")
                        
                        

                elif obj_type == "SCHEMA":
                    
                    if "all" in obj_name:
                        obj_types = obj_type.upper() + 'S'
                        cursor.execute(f"SHOW {obj_types} IN DATABASE {database_name}")
                        object_names = [row[1] for row in cursor.fetchall()]
                        for objname in object_names:
                            if objname not in ["INFORMATION_SCHEMA", "PUBLIC"]:
                                if enforcement_action == "ENFORCE":
                                    previous_grants = get_current_grants(cursor, obj_type, objname, grantee_type, grantee_name, database_name)
                                    try:
                                        cursor.execute(f"REVOKE ALL PRIVILEGES ON SCHEMA {database_name}.{objname} FROM {grantee_type} {database_name}.{grantee_name}")
                                        cursor.execute(f"GRANT {', '.join(privileges).upper()} ON SCHEMA {database_name}.{objname} TO {grantee_type} {database_name}.{grantee_name}")
                                    except Exception as e:
                                        # Restore previous grants if any failure occurs
                                        restore_previous_grants(cursor, obj_type, objname, previous_grants, grantee_type, grantee_name, database_name=database_name)
                                elif enforcement_action == "MERGE":
                                    # Apply the new grants
                                    cursor.execute(f"GRANT {', '.join(privileges).upper()} ON SCHEMA {database_name}.{objname} TO {grantee_type} {database_name}.{grantee_name}")

                    else:

                        for schema in obj_name:
                            if enforcement_action == "ENFORCE":
                                previous_grants = get_current_grants(cursor, obj_type, schema, grantee_type, grantee_name, database_name)
                                try:
                                    cursor.execute(f"REVOKE ALL PRIVILEGES ON SCHEMA {database_name}.{schema} FROM {grantee_type} {database_name}.{grantee_name}")
                                    cursor.execute(f"GRANT {', '.join(privileges).upper()} ON SCHEMA {database_name}.{schema} TO {grantee_type} {database_name}.{grantee_name}")
                                except Exception as e:
                                    # Restore previous grants if any failure occurs
                                    restore_previous_grants(cursor, obj_type, schema, previous_grants, grantee_type, grantee_name, database_name=database_name)
                            elif enforcement_action == "MERGE":
                                # Apply the new grants
                                cursor.execute(f"GRANT {', '.join(privileges).upper()} ON SCHEMA {database_name}.{schema} TO {grantee_type} {database_name}.{grantee_name}")

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
                            
    finally:
        cursor.close()


def funcational_role_assignment(conn, json_file):

    with open(json_file, 'r') as f:
        json_data = json.load(f)
    
        
    cursor = conn.cursor()

    cursor.execute("USE ROLE SECURITYADMIN")
    cursor.execute("USE WAREHOUSE COMPUTE_WH")
    cursor.execute(f"USE DATABASE SNOWFLAKE")

    for role in json_data['roles']:
        functional_role = role.get("functional_role")

        database_roles = role.get("database_roles")
        standard_roles = role.get("standard_roles")

        if database_roles:
            for db_name, db_roles in database_roles.items():
                for db_role in db_roles:
                    cursor.execute(f"GRANT DATABASE ROLE {db_name}.{db_role} TO ROLE {functional_role}")
        elif standard_roles:
            for r in standard_roles:
                cursor.execute(f"GRANT ROLE {r} TO ROLE {functional_role}")

    cursor.close()

    

if __name__ == "__main__":
    changed_files = sys.argv[1]
    connection = snowflake.connector.connect(
        user=sys.argv[2],
        password=sys.argv[3],
        account=sys.argv[4],
        role='SYSADMIN',
        warehouse='MANI_L_WH',
        database='MANI_DB',
        schema='MANI_SCHEMA'
    )

    #json_file_path = "snowflake_automation_scripts\database_roles_config.json"

    #role_mapping_json_path = "snowflake_automation_scripts\\role_mapping_config.json"
    files_list  = changed_files.split()
    for file in files_list:
        grant_permissions_from_json(connection, file)
    #funcational_role_assignment(connection, role_mapping_json_path)
    connection.close()
