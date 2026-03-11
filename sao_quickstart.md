# State-Aware Orchestration (SAO) & Freshness Configuration Guide

This README provides a practical overview of how to configure **source freshness**, **model freshness**, and **state-aware orchestration (SAO)** in dbt, including:
- Complete configuration patterns for source + model freshness  
- How SAO makes decisions  
- A hands-on experiment checklist  
- Recommended defaults and practical caveats  

Use this as a foundational guide for adopting and validating SAO in your dbt project.

---

# **1. Source Freshness**

Source freshness defines when upstream raw data is considered “fresh enough.” SAO uses source freshness (combined with state and model rules) to decide whether downstream models should be rebuilt.

You can configure freshness at either:
- the **source level** (applies to all tables), or  
- the **table level** (override source settings).

Freshness requires specifying **both** `count` and `period` unless setting `freshness: null`.

---

## **1.1 Source-Level Freshness Example**

```yaml
sources:
  - name: raw
    loaded_at_field: _etl_loaded_at
    config:
      freshness:
        warn_after: {count: 12, period: hour}
        error_after: {count: 24, period: hour}
```

---

## **1.2 Table-Level Override**

```yaml
sources:
  - name: raw
    tables:
      - name: orders
        config:
          freshness:
            warn_after: {count: 6, period: hour}
            filter: datediff('day', _etl_loaded_at, current_timestamp) < 2
```

Key notes:
- Table-level freshness overrides source-level settings.
- `filter:` reduces warehouse scan cost for large/partitioned tables.
- `filter:` does **not** apply if using a `loaded_at_query`.

---

## **1.3 Custom SQL Freshness (`loaded_at_query`)**

Use this when ingestion is partial, delayed, or requires custom logic.

```yaml
loaded_at_query: |
  select max(_sdc_batched_at) from {{ this }}
```

Notes:
- Overrides `loaded_at_field` if both are defined (closest rule wins).
- Ignores `filter:`
- Useful for late-arriving data or row-volume thresholds.

---

## **1.4 Metadata-Based Freshness**

If `loaded_at_field` is omitted and your adapter supports it, dbt uses warehouse metadata.

Supported on:
- Snowflake
- Redshift
- BigQuery (dbt-bigquery ≥ 1.7.3)
- Databricks (Fusion Engine)

---

# **2. Model Freshness (`build_after`)**

Model freshness controls **how often** a model may be rebuilt, even if upstream data changes frequently.

A model is eligible for rebuild when:
1. Upstream sources/models have *new data*, and  
2. Enough time has passed since the model was last built (`count` + `period`), and  
3. The `updates_on` condition is satisfied.

---

## **2.1 Example: Build No More Often Than Every 4 Hours**

```yaml
models:
  - name: stg_orders
    config:
      freshness:
        build_after:
          count: 4
          period: hour
          updates_on: all
```

---

## **2.2 `updates_on` Options**

| Value | Behavior |
|-------|----------|
| **any** | model rebuilds when *any one* upstream has new data |
| **all** | model rebuilds only when *all* upstreams have new data |

`any` = fresher data → more cost  
`all` = fewer builds → lower cost  

---

# **3. Project-Level Defaults and Overrides**

Use `dbt_project.yml` to set org-wide defaults, then override at folder or model level.

---

## **3.1 Project-Level Default (Recommended)**

```yaml
models:
  +freshness:
    build_after:
      count: 4
      period: hour
      updates_on: all
```

---

## **3.2 Folder-Level Override**

```yaml
models:
  marts:
    +freshness:
      build_after:
        count: 1
        period: hour
        updates_on: any
```

---

## **3.3 Disable Freshness Entirely**

```yaml
models:
  - name: product_skus
    config:
      freshness: null
```

Disabling freshness returns the model to SAO’s default behavior:
- Rebuild when code OR upstream data changes  
- No time-gating  

---

# **4. SAO Experiment Checklist**

> Use this checklist to understand how SAO behaves under different conditions.

---

## **4.1 Source Freshness Experiments**

[ ] Add source-level `warn_after` and `error_after`
[ ] Add `loaded_at_field` at the source level  
[ ] Remove `loaded_at_field` to test metadata-based freshness  
[ ] Add table-level freshness override  
[ ] Add a `filter:` to reduce scanned partitions  
[ ] Add a `loaded_at_query` and observe behavior  
[ ] Compare compiled SQL under each configuration  

---

## **4.2 Model Freshness Experiments**

[ ] Add `build_after` to one model  
[ ] Run a job → confirm it builds  
[ ] Run the job again immediately → confirm it skips (time-gated)  
[ ] Change `updates_on` to `any` → observe rebuild behavior  
[ ] Change `updates_on` to `all` → observe gating behavior  
[ ] Set project-level freshness defaults  
[ ] Override freshness at folder level  
[ ] Override at model level  
[ ] Disable freshness for one model using `freshness: null`  

---

## **4.3 SAO Behavior Experiments**

[ ] Run a job twice with no data/code changes → confirm SAO skips builds  
[ ] Modify upstream source data → confirm SAO rebuilds  
[ ] Modify model SQL → confirm rebuild regardless of freshness  
[ ] Mix fresh + stale upstreams → observe differences between `any` vs `all`  
[ ] Change job frequency (e.g., 30 minutes) → observe `build_after` enforcement  

---

## **4.4 SAO Limitations & Edge Cases**

[ ] Delete a warehouse table → confirm SAO does **not** detect this  
[ ] Clear environment cache → confirm rebuild on next run  
[ ] Temporarily disable SAO → confirm forced rebuild behavior  
[ ] Add sources that are warehouse views → observe “always fresh” warning  

---

# **5. Recommended Starting Configuration**

A balanced, cost-efficient configuration for most teams:

---

## **5.1 Sources**

```yaml
sources:
  - name: raw
    loaded_at_field: _etl_loaded_at
    config:
      freshness:
        warn_after: {count: 12, period: hour}
        error_after: {count: 24, period: hour}
```

---

## **5.2 Models**

```yaml
models:
  +freshness:
    build_after:
      count: 4
      period: hour
      updates_on: all
```

---

## **5.3 High-Priority Models**

```yaml
models:
  - name: fact_orders
    config:
      freshness:
        build_after:
          count: 1
          period: hour
          updates_on: any
```

---

# **6. Limitations**

SAO **does not detect deleted warehouse tables** unless:
- You clear environment cache, or  
- You disable SAO temporarily.

Other limitations:
- `loaded_at_query` overrides `loaded_at_field`.  
- `filter:` is ignored when using `loaded_at_query`.  
- Views without freshness configs are treated as “always fresh.”  