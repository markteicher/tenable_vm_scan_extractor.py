#!/usr/bin/env python3

"""
=====================================================================
Script Name:
tenable_vm_scan_extractor.py
=====================================================================

Purpose:
Framework to extract Tenable VM scan inventory and scan detail metadata,
merge the data, and export for analysis
Implements three passes:
Pass 1: Export List of Scans to a CSV
Pass 2: Builds Scan details from scan_id to CSV
Pass 3: Merge CSVs

Logging:
- Console Logging
- Writes to logfile
- Unix Standard log format
- Severity: INFO, WARN, ERROR, CRIT, DEBUG
=====================================================================
"""

import os
import sys
import time
import csv
import logging
import requests
from tqdm import tqdm
from colorama import init

init(autoreset=True)

# ===============================
# CONFIGURATION
# ===============================
SCRIPT_NAME = os.path.splitext(os.path.basename(__file__))[0]
LOG_FILE = f"{SCRIPT_NAME}.log"

BASE_URL = "https://cloud.tenable.com"
ACCESS_KEY = "ACCESS_KEY"
SECRET_KEY = "SECRET_KEY"

PROXIES = {"http": "http://proxy.company.com:8080", "https": "http://proxy.company.com:8080"}

HEADERS = {"accept": "application/json", "X-ApiKeys": f"accessKey={ACCESS_KEY}; secretKey={SECRET_KEY}"}

# ===============================
# LOGGING
# ===============================
logger = logging.getLogger(SCRIPT_NAME)
logger.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s[%(process)d]: %(message)s")
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)
file_handler = logging.FileHandler(LOG_FILE)
file_handler.setFormatter(formatter)
logger.addHandler(console_handler)
logger.addHandler(file_handler)

# ===============================
# REQUIRED PACKAGE VALIDATION
# ===============================
required_packages = ["requests", "tqdm", "colorama"]
missing_packages = []

for pkg in required_packages:
try:
__import__(pkg)
except ImportError:
missing_packages.append(pkg)

if missing_packages:
logger.critical(f"Missing required packages: {', '.join(missing_packages)}")
logger.critical("Please install missing packages before running the script.")
sys.exit(1)
else:
logger.info(f"All required packages installed: {', '.join(required_packages)}")

# ===============================
# VALIDATION FUNCTIONS
# ===============================
def validate_response(response, context):
if response.status_code == 200:
return
mapping = {400:"Bad Request",401:"Unauthorized",403:"Forbidden",404:"Not Found",429:"Rate Limited"}
msg = mapping.get(response.status_code,f"HTTP {response.status_code} Server Error")
if response.status_code >= 500:
logger.critical(f"{context} - {msg}")
else:
logger.error(f"{context} - {msg}")
raise Exception(f"{context} failed")

def validate_proxy():
logger.info("Validating proxy configuration")
requests.get("https://www.google.com", proxies=PROXIES, timeout=10)
logger.info("Proxy validation successful")

def validate_api():
logger.info("Validating API connectivity")
response = requests.get(f"{BASE_URL}/scans", headers=HEADERS, proxies=PROXIES, timeout=15)
validate_response(response,"GET /scans")
logger.info("API validation successful")

# ===============================
# API FUNCTIONS
# ===============================
def get_scans():
response = requests.get(f"{BASE_URL}/scans", headers=HEADERS, proxies=PROXIES, timeout=30)
validate_response(response,"GET /scans")
return response.json().get("scans", [])

def get_scan_details(scan_id):
response = requests.get(f"{BASE_URL}/scans/{scan_id}", headers=HEADERS, proxies=PROXIES, timeout=30)
validate_response(response,f"GET /scans/{scan_id}")
return response.json()

# ===============================
# FLATTENER HELPER
# ===============================
def flatten_json(y, prefix=''):
out = {}
if isinstance(y, dict):
for k,v in y.items():
out.update(flatten_json(v,f"{prefix}{k}_"))
elif isinstance(y,list):
for i,v in enumerate(y):
out.update(flatten_json(v,f"{prefix}{i}_"))
else:
out[prefix[:-1]] = y
return out

# ===============================
# MAIN FUNCTION
# ===============================
def main():
logger.info("START")
validate_proxy()
validate_api()

# ===============================
# PASS 1 - OBTAIN LIST OF SCANS
# ===============================
logger.info("PASS 1 MODULE STARTED")
pass1_start = time.time()
scan_list_metrics = {"records_processed":0,"records_failed":0,"records_written":0,"execution_time_seconds":None}
try:
scans = get_scans()
records_pass1=[]
for scan in tqdm(scans, desc="Processing inventory scans"):
scan_list_metrics["records_processed"] += 1
try:
records_pass1.append(flatten_json(scan))
scan_list_metrics["records_written"] += 1
except Exception as e:
scan_list_metrics["records_failed"] += 1
logger.error(f"Failed processing scan {scan.get('id')}: {e}")

pass1_end = time.time()
scan_list_metrics["execution_time_seconds"] = round(pass1_end-pass1_start,2)
pass1_file = "tenable_vm_scans_inventory.csv"
if records_pass1:
fieldnames=list({k for r in records_pass1 for k in r.keys()})
with open(pass1_file,"w",newline="", encoding="utf-8") as f:
writer=csv.DictWriter(f, fieldnames=fieldnames)
writer.writeheader()
writer.writerows(records_pass1)
logger.info(f"PASS 1 start: {time.strftime('%Y-%m-%d %H:%M:%S',time.localtime(pass1_start))}, end: {time.strftime('%Y-%m-%d %H:%M:%S',time.localtime(pass1_end))}, execution (s): {scan_list_metrics['execution_time_seconds']}")
logger.info(f"Pass 1 metrics: {scan_list_metrics}")
except Exception as e:
scan_list_metrics["records_failed"]=1
logger.critical(f"Pass 1 failed: {e}")
return
logger.info("PASS 1 MODULE ENDED")

# ===============================
# PASS 2 - USE SCAN_ID TO OBTAIN SCAN DETAILS
# ===============================
logger.info("PASS 2 MODULE STARTED")
pass2_start = time.time()
scan_processing_metrics={"records_processed":0,"records_failed":0,"records_written":0,"execution_time_seconds":None}
records_pass2=[]
try:
scan_ids = [row["id"] for row in csv.DictReader(open(pass1_file, encoding="utf-8"))]
for scan_id in tqdm(scan_ids, desc="Processing scan details"):
scan_processing_metrics["records_processed"] += 1
try:
details=get_scan_details(scan_id)
flat_details=flatten_json(details)
flat_details["export_timestamp"]=int(time.time())
records_pass2.append(flat_details)
scan_processing_metrics["records_written"] += 1
except Exception as e:
scan_processing_metrics["records_failed"] += 1
logger.error(f"Scan {scan_id} failed: {e}")

pass2_end=time.time()
scan_processing_metrics["execution_time_seconds"]=round(pass2_end-pass2_start,2)
pass2_file="tenable_vm_scans_details.csv"
if records_pass2:
fieldnames=list({k for r in records_pass2 for k in r.keys()})
with open(pass2_file,"w",newline="",encoding="utf-8") as f:
writer=csv.DictWriter(f,fieldnames=fieldnames)
writer.writeheader()
writer.writerows(records_pass2)
logger.info(f"PASS 2 start: {time.strftime('%Y-%m-%d %H:%M:%S',time.localtime(pass2_start))}, end: {time.strftime('%Y-%m-%d %H:%M:%S',time.localtime(pass2_end))}, execution (s): {scan_processing_metrics['execution_time_seconds']}")
logger.info(f"Pass 2 metrics: {scan_processing_metrics}")
except Exception as e:
logger.critical(f"Pass 2 failed: {e}")
return
logger.info("PASS 2 MODULE ENDED")

# ===============================
# PASS 3 - MERGE LIST OF SCANS AND SCAN DETAILS
# ===============================
logger.info("PASS 3 MODULE STARTED")
pass3_start=time.time()
merge_metrics={"records_merged":0,"execution_time_seconds":None}
try:
inventory_rows=list(csv.DictReader(open(pass1_file,encoding="utf-8")))
details_rows=list(csv.DictReader(open(pass2_file,encoding="utf-8")))
details_dict={row["info_id"]:row for row in details_rows}

merged_rows=[]
for inv_row in tqdm(inventory_rows, desc="Merging CSVs"):
scan_id = inv_row["id"]
merged_row = inv_row.copy()
if scan_id in details_dict:
merged_row.update(details_dict[scan_id])
merged_rows.append(merged_row)

final_file="tenable_vm_scans_merged.csv"
fieldnames=list({k for r in merged_rows for k in r.keys()})
with open(final_file,"w",newline="",encoding="utf-8") as f:
writer=csv.DictWriter(f,fieldnames=fieldnames)
writer.writeheader()
writer.writerows(merged_rows)

pass3_end=time.time()
merge_metrics["records_merged"]=len(merged_rows)
merge_metrics["execution_time_seconds"]=round(pass3_end-pass3_start,2)
logger.info(f"PASS 3 start: {time.strftime('%Y-%m-%d %H:%M:%S',time.localtime(pass3_start))}, end: {time.strftime('%Y-%m-%d %H:%M:%S',time.localtime(pass3_end))}, execution (s): {merge_metrics['execution_time_seconds']}")
logger.info(f"Pass 3 metrics: {merge_metrics}")
logger.info(f"Pass 3 merge CSV written: {final_file}")
except Exception as e:
logger.critical(f"Pass 3 merge failed: {e}")
return
logger.info("PASS 3 MODULE ENDED")
logger.info("COMPLETE")

if __name__=="__main__":
main()
