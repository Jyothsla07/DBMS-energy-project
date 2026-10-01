-- 03_analysis_queries.sql  (MySQL 8.0+)
-- Energy analysis queries on the energy_reading table.
-- Note: each row is a 5-minute reading in MW, so energy (MWh) = MW * 5/60.

-- =====================================================================
-- Q1. Dataset overview: size, date range, and average values
-- =====================================================================
SELECT COUNT(*)                        AS total_readings,
       MIN(reading_time)               AS first_reading,
       MAX(reading_time)               AS last_reading,
       ROUND(AVG(electric_demand), 0)  AS avg_demand_mw,
       MAX(electric_demand)            AS peak_demand_mw,
       ROUND(AVG(pv_production), 0)    AS avg_solar_mw,
       ROUND(AVG(wind_production), 0)  AS avg_wind_mw
FROM energy_reading;

-- =====================================================================
-- Q2. Yearly totals: energy demand vs solar and wind production (GWh)
-- =====================================================================
SELECT YEAR(reading_time)                                  AS year,
       ROUND(SUM(electric_demand) * 5 / 60 / 1000, 0)      AS demand_gwh,
       ROUND(SUM(pv_production)   * 5 / 60 / 1000, 0)      AS solar_gwh,
       ROUND(SUM(wind_production) * 5 / 60 / 1000, 0)      AS wind_gwh
FROM energy_reading
GROUP BY YEAR(reading_time)
ORDER BY year;

-- =====================================================================
-- Q3. Daily demand profile: average demand for each hour of the day
-- =====================================================================
SELECT HOUR(reading_time)              AS hour_of_day,
       ROUND(AVG(electric_demand), 0)  AS avg_demand_mw
FROM energy_reading
GROUP BY HOUR(reading_time)
ORDER BY hour_of_day;

-- =====================================================================
-- Q4. Seasonal comparison (JOIN with the season lookup table)
-- =====================================================================
SELECT s.season_name,
       s.months,
       ROUND(AVG(e.electric_demand), 0) AS avg_demand_mw,
       ROUND(AVG(e.pv_production), 0)   AS avg_solar_mw,
       ROUND(AVG(e.wind_production), 0) AS avg_wind_mw,
       ROUND(AVG(e.temperature), 1)     AS avg_temp
FROM energy_reading e
JOIN season s ON e.season_id = s.season_id
GROUP BY s.season_id, s.season_name, s.months
ORDER BY s.season_id;

-- =====================================================================
-- Q5. Weekday vs weekend demand (JOIN with the day_of_week lookup table)
-- =====================================================================
SELECT CASE WHEN d.is_weekend THEN 'Weekend' ELSE 'Weekday' END AS day_type,
       ROUND(AVG(e.electric_demand), 0) AS avg_demand_mw,
       MAX(e.electric_demand)           AS peak_demand_mw
FROM energy_reading e
JOIN day_of_week d ON e.day_id = d.day_id
GROUP BY day_type;

-- =====================================================================
-- Q6. Monthly renewable share: % of demand covered by solar + wind
-- =====================================================================
SELECT DATE_FORMAT(reading_time, '%Y-%m')                          AS month,
       ROUND(100 * SUM(pv_production) / SUM(electric_demand), 1)   AS solar_pct,
       ROUND(100 * SUM(wind_production) / SUM(electric_demand), 1) AS wind_pct,
       ROUND(100 * SUM(pv_production + wind_production)
                 / SUM(electric_demand), 1)                        AS renewable_pct
FROM energy_reading
GROUP BY DATE_FORMAT(reading_time, '%Y-%m')
ORDER BY month;

-- =====================================================================
-- Q7. Top 10 highest-demand days
-- =====================================================================
SELECT DATE(reading_time)              AS day,
       MAX(electric_demand)            AS peak_demand_mw,
       ROUND(AVG(electric_demand), 0)  AS avg_demand_mw,
       ROUND(MAX(temperature), 1)      AS max_temp
FROM energy_reading
GROUP BY DATE(reading_time)
ORDER BY peak_demand_mw DESC
LIMIT 10;

-- =====================================================================
-- Q8. Effect of temperature on demand (temperature bands)
-- =====================================================================
SELECT CASE
           WHEN temperature < 10 THEN '1: below 10'
           WHEN temperature < 20 THEN '2: 10-20'
           WHEN temperature < 30 THEN '3: 20-30'
           ELSE                       '4: 30 and above'
       END                              AS temp_band,
       COUNT(*)                         AS readings,
       ROUND(AVG(electric_demand), 0)   AS avg_demand_mw
FROM energy_reading
GROUP BY temp_band
ORDER BY temp_band;

-- =====================================================================
-- Q9. Solar production vs irradiance (GHI bands)
-- =====================================================================
SELECT FLOOR(ghi / 200) * 200            AS ghi_band_start,
       COUNT(*)                          AS readings,
       ROUND(AVG(pv_production), 0)      AS avg_solar_mw
FROM energy_reading
GROUP BY ghi_band_start
ORDER BY ghi_band_start;

-- =====================================================================
-- Q10. "Duck curve": net load (demand minus solar and wind) by hour
-- Shows how solar lowers the load other power plants must supply
-- around midday, followed by a steep evening ramp.
-- =====================================================================
SELECT HOUR(reading_time)                                             AS hour_of_day,
       ROUND(AVG(electric_demand), 0)                                 AS avg_demand_mw,
       ROUND(AVG(electric_demand - pv_production - wind_production), 0) AS avg_net_load_mw
FROM energy_reading
GROUP BY HOUR(reading_time)
ORDER BY hour_of_day;

-- =====================================================================
-- Q11. Window function: rolling 1-hour average demand for one day
-- (12 readings x 5 minutes = 1 hour)
-- =====================================================================
SELECT reading_time,
       electric_demand,
       ROUND(AVG(electric_demand) OVER (
             ORDER BY reading_time
             ROWS BETWEEN 11 PRECEDING AND CURRENT ROW), 0) AS rolling_1h_avg_mw
FROM energy_reading
WHERE reading_time >= '2021-07-15' AND reading_time < '2021-07-16'
ORDER BY reading_time;

-- =====================================================================
-- Q12. Window function: largest 5-minute ramps in demand (LAG)
-- =====================================================================
WITH ramps AS (
    SELECT reading_time,
           electric_demand,
           electric_demand - LAG(electric_demand) OVER (ORDER BY reading_time)
               AS change_mw
    FROM energy_reading
)
SELECT reading_time, electric_demand, change_mw
FROM ramps
WHERE change_mw IS NOT NULL
ORDER BY ABS(change_mw) DESC
LIMIT 10;
