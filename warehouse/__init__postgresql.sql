/*
=============================================================
Create Database and Schemas
=============================================================
Script Purpose:
    This script creates a new database named 'Japan Car Import Advisory Platform' after checking if it already exists. 
    If the database exists, it is dropped and recreated. Additionally, the script sets up three schemas 
    within the database: 'bronze', 'silver', and 'gold'.
	
WARNING:
    Running this script will drop the entire 'Japan Car Import Advisory Platform' database if it exists. 
    All data in the database will be permanently deleted. Proceed with caution 
    and ensure you have proper backups before running this script.
*/
DROP DATABASE IF EXISTS japan_car_import_database;
CREATE DATABASE japan_car_import_database;

\c japan_car_import_database;

CREATE SCHEMA IF NOT EXISTS bronze;

SELECT schema_name
FROM Information_schema.schemata
WHERE schema_name IN 
    ("bronze", "silver", "gold")
    