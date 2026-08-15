import os
import sys
import datetime

# Ensure local suite directory is on python path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

import generate_unified_report
import generate_kanshi_standalone

def parse_target_date(arg=None):
    now_utc = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    now_ist = now_utc + datetime.timedelta(hours=5, minutes=30)
    
    if not arg or arg.lower() == 'today':
        return now_ist.strftime('%Y-%m-%d')
    elif arg.lower() == 'yesterday':
        yesterday_ist = (now_ist - datetime.timedelta(days=1)).date()
        return yesterday_ist.strftime('%Y-%m-%d')
    elif arg.lower() == '24h':
        return '24h'
    else:
        # Validate YYYY-MM-DD format
        try:
            parsed = datetime.datetime.strptime(arg, '%Y-%m-%d').date()
            return parsed.strftime('%Y-%m-%d')
        except ValueError:
            print(f"Warning: '{arg}' is not a valid YYYY-MM-DD format. Defaulting to today ({now_ist.strftime('%Y-%m-%d')}).")
            return now_ist.strftime('%Y-%m-%d')

def run_daily_reports(target_date_str=None):
    target_date_str = parse_target_date(target_date_str)

    print(f"==================================================")
    print(f"RUNNING MASTER REPORT GENERATION FOR: {target_date_str}")
    print(f"==================================================")

    # 1. Generate Unified Multi-Store Sales Report
    print(f"\n[1/2] Generating Unified Multi-Store Sales Report...")
    generate_unified_report.generate_unified_report(target_date_str)

    # 2. Generate Standalone Kanshi Jewels Sales Report
    print(f"\n[2/2] Generating Standalone Kanshi Jewels Sales Report...")
    generate_kanshi_standalone.generate_kanshi_standalone(target_date_str)

    suffix = "24h" if target_date_str == "24h" else target_date_str.replace('-', '')
    print(f"\n==================================================")
    print(f"  [+] ALL REPORTS SUCCESSFULLY GENERATED FOR {target_date_str}")
    print(f"  - multi_store_sales_report_{suffix}.html")
    print(f"  - kanshi_sales_report_{suffix}.html")
    print(f"==================================================")

if __name__ == '__main__':
    date_arg = sys.argv[1] if len(sys.argv) > 1 else 'today'
    run_daily_reports(date_arg)
