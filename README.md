# 🚀 AI-Powered Marketing Analytics Pipeline

### End-to-End Data Engineering + BI + AI Insight System

---

## 📌 Overview

This project is a **complete marketing analytics pipeline** that transforms raw ad and sales data into:

* 📊 **Interactive dashboards (Power BI)**
* 🧠 **AI-generated business insights (LLM-based tool)**

The system ensures a **single source of truth (SQL database)** and follows a **production-style data workflow** used in real-world marketing analytics teams.

---

## 🎯 Objectives

* Clean and validate messy ad platform & Shopify data
* Build a structured **data warehouse (SQL)**
* Create **business dashboards (Power BI)**
* Develop an **AI tool that answers natural language queries using SQL + LLM**

---

## 🏗️ Architecture

```
Raw CSV Data
   ↓
Python (Data Cleaning & Validation)
   ↓
SQL Database (PostgreSQL - Single Source of Truth)
   ↓                ↓
Power BI          AI Insight Tool (LLM)
(Dashboard)       (Natural Language → SQL → Answer)
```

---

## 🔄 End-to-End Pipeline Flow

### 🔹 Step 1 — Raw Data

* Input:

  * Campaign data (Meta Ads export)
  * Shopify sales data
* Issues:

  * Missing values
  * Duplicate rows
  * Inconsistent formats
  * Incorrect calculated metrics

---

### 🔹 Step 2 — Python Data Cleaning (Pandas)

✔ Tasks performed:

* Removed duplicate records
* Standardized date formats
* Handled missing values (based on business logic)
* Recalculated key metrics:

  * CTR
  * CPC
  * CPM
  * ROI
* Normalized categorical fields (platform, region, status)

📦 Output:

* Cleaned datasets
* Ready for SQL ingestion

---

### 🔹 Step 3 — SQL Data Warehouse (PostgreSQL)

✔ Designed a **Star Schema**:

#### Fact Table:

* `fact_ads` → stores performance metrics

#### Dimension Tables:

* `dim_campaign`
* `dim_date`

✔ Features:

* Aggregated metrics for analysis
* Indexed columns for fast queries
* Clean naming conventions

📊 Example Metrics:

* Spend
* Clicks
* Impressions
* Purchases
* Revenue
* CTR, CPC, ROI

---

### 🔹 Step 4 — Power BI Dashboard

✔ Connected directly to SQL (no CSV dependency)

### 📄 Dashboard Pages:

#### 1. Executive Summary

* KPI Cards:

  * Total Spend
  * Revenue
  * Conversions
  * ROI / ROAS
* Monthly trend (Spend vs Conversions)
* Top campaigns

#### 2. Channel & Platform Analysis

* Platform performance (Spend vs Revenue)
* Channel mix (Donut chart)
* Region-wise matrix

#### 3. Audience Insights

* Conversion by region
* Spend vs conversions scatter plot

✔ Features:

* Cross-page slicers (Date, Platform)
* Clean visual storytelling

---

### 🔹 Step 5 — AI Insight Tool (LLM over SQL)

A Streamlit-based application that allows users to **ask questions in plain English**.

---

## 🧠 How the AI Tool Works

```
User Question
   ↓
LLM generates SQL query
   ↓
SQL runs on database
   ↓
Result passed to LLM
   ↓
Final business insight generated
```

---

## 💡 Example Questions

* "Which campaign had the worst CPC in March?"
* "Summarise UK region performance"
* "Top 5 campaigns by ROI"
* "Compare platform performance"

---

## 🛠️ Tech Stack

| Layer         | Tools Used                |
| ------------- | ------------------------- |
| Data Cleaning | Python, Pandas            |
| Database      | PostgreSQL                |
| BI Tool       | Power BI                  |
| AI Tool       | Streamlit + Gemini API    |
| Query Engine  | SQL (Text-to-SQL via LLM) |

---

## 📂 Project Structure

```
├── data/
│   ├── raw_campaign.csv
│   ├── raw_shopify.csv
│
├── notebooks/
│   ├── Campaign_Data_Cleaning.ipynb
│   ├── Shopify_Data_Cleaning.ipynb
│
├── sql/
│   └── schema.sql
│
├── powerbi/
│   ├── Marketing_Assignment.pbix
│   └── dashboard_export.pdf
│
├── ai_tool/
│   ├── app.py
│   ├── db.py
│   ├── llm.py
│   ├── query_generator.py
│
├── requirements.txt
└── README.md
```

---

## ⚙️ Setup Instructions

### 1️⃣ Clone Repository

```bash
git clone <https://github.com/vinayakjain01/AI-Powered-Marketing-Analytics-System.git>
cd marketing-analytics-pipeline
```

---

### 2️⃣ Install Dependencies

```bash
pip install -r requirements.txt
```

---

### 3️⃣ Setup Database (PostgreSQL)

* Create database: `campaign`
* Run:

```sql
schema.sql
```

---

### 4️⃣ Load Cleaned Data

* Run Python notebooks to generate cleaned datasets
* Insert into `staging_ads`

---

### 5️⃣ Run AI Tool

```bash
streamlit run app.py
```

---

## 🔐 Environment Variables (IMPORTANT)

Create a `.env` file:

```
GEMINI_API_KEY=your_api_key_here
DB_HOST=localhost
DB_NAME=campaign
DB_USER=postgres
DB_PASSWORD=your_password
```

---

## 📊 Key Features

✔ End-to-end pipeline (raw → insights)
✔ SQL as single source of truth
✔ Production-style data modeling
✔ Power BI storytelling dashboards
✔ AI-powered query system (Text → SQL → Insight)

---

## ⚠️ Challenges & Solutions

| Challenge         | Solution                               |
| ----------------- | -------------------------------------- |
| Dirty raw data    | Built robust cleaning pipeline         |
| Incorrect metrics | Recalculated from base columns         |
| Slow queries      | Added indexes                          |
| LLM hallucination | Restricted prompt + SQL-first approach |

---

## 🚀 Future Improvements

* Add conversation memory in AI tool
* Improve query validation & security
* Deploy on cloud (AWS / GCP)
* Add real-time data pipeline

---

## 👨‍💻 Author

**Vinayak Jain**

Data Analyst

vinayakjainn11@gmail.com

LinkedIn - www.linkedin.com/in/vinayak-jain-69801b328

---

👉 Built with a focus on **real-world marketing analytics use cases**.

---
