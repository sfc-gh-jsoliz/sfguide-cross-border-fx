-- ============================================================================
-- Cross-Border & FX — teardown.sql
-- ----------------------------------------------------------------------------
-- Removes everything created by setup.sql / setup_synthetic.sql: the dedicated
-- database (with all tables, views, the semantic view and the agent) and the
-- dedicated warehouse. Safe to re-run.
-- ============================================================================

DROP DATABASE IF EXISTS SNOWPACK_CROSS_BORDER_FX;
DROP WAREHOUSE IF EXISTS SNOWPACK_CROSS_BORDER_FX_WH;
