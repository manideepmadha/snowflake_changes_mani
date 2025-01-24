import snowflake.connector
import json
import re
import sys
import logging


def create_warehouses_from_json(connection, json_file):
    
    with open(json_file, 'r') as f:
        json_data = json.load(f)
    
    cursor = connection.cursor()
    messages = []
    
    for warehouse in json_data.get("warehouses", []):
        warehouse_name = warehouse.get("warehouse_name")
        warehouse_size = warehouse.get("warehouse_size", "XSMALL")
        initially_suspended = warehouse.get("initially_suspended", True)
        max_cluster_count = warehouse.get("max_cluster_count", 1)
        min_cluster_count = warehouse.get("min_cluster_count", 1)
        auto_suspend = warehouse.get("auto_suspend", 300)
        scaling_policy = warehouse.get("scaling_policy", "STANDARD")
        comment = warehouse.get("comment", "")

        initially_suspended_str = 'TRUE' if initially_suspended else 'FALSE'

        create_sql = f"""
        CREATE WAREHOUSE IF NOT EXISTS {warehouse_name}
        WITH WAREHOUSE_SIZE = {warehouse_size}
        INITIALLY_SUSPENDED = {initially_suspended_str}
        MAX_CLUSTER_COUNT = {max_cluster_count}
        MIN_CLUSTER_COUNT = {min_cluster_count}
        AUTO_SUSPEND = {auto_suspend}
        SCALING_POLICY = '{scaling_policy}'
        COMMENT = '{comment}';
        """
        cursor.execute(create_sql)
        
        messages.append(f"SUCCESS: {create_sql}")
        print(f"Warehouse {warehouse_name} created successfully (if it did not already exist).")

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

        messages = create_warehouses_from_json(connection, file)
        print(messages)

    connection.close()
