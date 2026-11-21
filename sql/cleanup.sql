-- ============================================================================
-- Cross-Border & FX - sql/cleanup.sql
-- Removes everything sql/setup.sql created: the database (tables, views,
-- semantic view, agent, stage, Streamlit app), the warehouse and the role.
-- Objects are owned by CROSS_BORDER_FX_ROLE, so they are dropped as that role
-- first; ACCOUNTADMIN then drops the role. Run it as the user who ran setup.
-- ============================================================================
USE ROLE CROSS_BORDER_FX_ROLE;  -- granted to the user who ran setup
DROP DATABASE IF EXISTS SNOWPACK_CROSS_BORDER_FX;
DROP WAREHOUSE IF EXISTS SNOWPACK_CROSS_BORDER_FX_WH;
USE ROLE ACCOUNTADMIN;
DROP ROLE IF EXISTS CROSS_BORDER_FX_ROLE;
SHOW DATABASES LIKE 'SNOWPACK_CROSS_BORDER_FX';
