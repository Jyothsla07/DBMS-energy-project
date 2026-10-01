-- 01_schema.sql  (MySQL 8.0+)
-- Creates the tables for the energy database.
-- Run while connected to the energydb database.

DROP TABLE IF EXISTS energy_reading;
DROP TABLE IF EXISTS season;
DROP TABLE IF EXISTS day_of_week;

-- Lookup table: Season codes in the dataset are calendar quarters
CREATE TABLE season (
    season_id    TINYINT PRIMARY KEY,
    season_name  VARCHAR(20) NOT NULL,
    months       VARCHAR(20) NOT NULL
) ENGINE=InnoDB;

INSERT INTO season VALUES
    (1, 'Q1 (Winter)', 'Jan-Mar'),
    (2, 'Q2 (Spring)', 'Apr-Jun'),
    (3, 'Q3 (Summer)', 'Jul-Sep'),
    (4, 'Q4 (Autumn)', 'Oct-Dec');

-- Lookup table: Day_of_the_week codes (0 = Monday ... 6 = Sunday)
CREATE TABLE day_of_week (
    day_id      TINYINT PRIMARY KEY,
    day_name    VARCHAR(10) NOT NULL,
    is_weekend  BOOLEAN NOT NULL
) ENGINE=InnoDB;

INSERT INTO day_of_week VALUES
    (0, 'Monday',    FALSE),
    (1, 'Tuesday',   FALSE),
    (2, 'Wednesday', FALSE),
    (3, 'Thursday',  FALSE),
    (4, 'Friday',    FALSE),
    (5, 'Saturday',  TRUE),
    (6, 'Sunday',    TRUE);

-- Main table: one row per 5-minute reading
CREATE TABLE energy_reading (
    reading_time     DATETIME PRIMARY KEY,
    season_id        TINYINT NOT NULL,
    day_id           TINYINT NOT NULL,
    dhi              FLOAT,      -- Diffuse Horizontal Irradiance (W/m2)
    dni              FLOAT,      -- Direct Normal Irradiance (W/m2)
    ghi              FLOAT,      -- Global Horizontal Irradiance (W/m2)
    wind_speed       FLOAT,
    humidity         FLOAT,
    temperature      FLOAT,
    pv_production    INT,        -- solar production (MW)
    wind_production  INT,        -- wind production (MW)
    electric_demand  INT,        -- electricity demand (MW)
    FOREIGN KEY (season_id) REFERENCES season(season_id),
    FOREIGN KEY (day_id)    REFERENCES day_of_week(day_id)
) ENGINE=InnoDB;
