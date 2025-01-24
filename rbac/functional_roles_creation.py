import snowflake.connector
import json
import re
import sys
import logging


def create_role(cursor, role_name, comment):
    """Create a functional role in Snowflake with a comment."""
    msg = []
    query = f"CREATE ROLE IF NOT EXISTS {role_name} COMMENT = '{comment}'"
    cursor.execute(query)
    msg.append(query)
    query = f"GRANT ROLE {role_name} TO ROLE SYSADMIN"
    cursor.execute(query)
    msg.append(query)
    print(f"Role {role_name} created with comment: {comment}")
    
    return msg

def delete_role(cursor, role_name):
    """Delete a functional role in Snowflake."""
    msg = []
    query = f"DROP ROLE IF EXISTS {role_name}"
    cursor.execute(query)
    msg.append(query)
    print(f"Role {role_name} deleted.")
    return msg

def functional_role_creation(connection, json_file):
    """Read the JSON file and create or delete roles based on the action specified."""
    cursor = connection.cursor()
    messages = []

    with open(json_file, 'r') as f:
        data = json.load(f)

    for category, roles in data['roles'].items():
        print(f"\nProcessing {category} roles:")
        for role in roles:
            role_name = role['role_name']
            comment = role.get('comment', '')
            action = role['action'].lower()
            
            if action == 'create':
                msg = create_role(cursor, role_name, comment)
                messages+=msg
            elif action == 'delete':
                msg = delete_role(cursor, role_name)
                messages+=msg
            else:
                print(f"Unknown action '{action}' for role {role_name}. Skipping.")
    
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

        messages = functional_role_creation(connection, file)
        print(messages)

        connection.close()