import snowflake.connector
import json
import re
import sys
import logging

def functional_role_assignment(conn, json_file):

    with open(json_file, 'r') as f:
        json_data = json.load(f)
    
        
    cursor = conn.cursor()
    messages = []

    for role in json_data['roles']:
        functional_role = role.get("functional_role")

        warehouses = role.get("warehouses")

        for warehouse in warehouses:
            query = f"GRANT USAGE ON WAREHOUSE {warehouse} TO ROLE {functional_role}"
            cursor.execute(query)
            messages.append(f"SUCCESS: {query}")

        integrations = role.get("integrations")

        for integration in integrations:
        
            query = f"GRANT USAGE ON INTEGRATION {integration} TO ROLE {functional_role}"
            cursor.execute(query)
            messages.append(f"SUCCESS: {query}")


    for role in json_data['roles']:
        functional_role = role.get("functional_role")

        database_roles = role.get("database_roles")
        standard_roles = role.get("standard_roles")

        if database_roles:
            for db_name, db_roles in database_roles.items():
                for db_role in db_roles:
                    query = f"GRANT DATABASE ROLE {db_name}.{db_role} TO ROLE {functional_role}"
                    cursor.execute(query)
                    messages.append(f"SUCCESS: {query}")
        elif standard_roles:
            for r in standard_roles:
                query = f"GRANT ROLE {r} TO ROLE {functional_role}"
                cursor.execute(query)
                messages.append(f"SUCCESS: {query}")

    cursor.close()
    return messages


if __name__ == "__main__":
    
    connection = snowflake.connector.connect(
        user=sys.argv[2],
        password=sys.argv[3],
        account=sys.argv[4],
        role=sys.argv[5],
        warehouse='SVC_ETL_XS_WAREHOUSE',
        database='SNOWFLAKE',
        schema='INFORMATION_SCHEMA'
    )
    json_array = sys.argv[1]
    
    for file in json_array:

        messages = functional_role_assignment(connection, file)

        connection.close()