import streamlit as st
import pandas as pd
from datetime import datetime, time, timedelta

st.set_page_config(page_title="HR Payroll & Attendance Dashboard", layout="wide")

## 🏢 Header
st.title("💼 HR Attendance & Payroll Processing Hub")
st.markdown("Upload raw biometric logs to compute shifts, overtime, cross-midnight logs, and exact per-second salary adjustments.")
st.write("---")

## ⚙️ Payroll Policy Settings
st.sidebar.header("⚙️ Payroll Configuration")
base_monthly_salary = st.sidebar.number_input("Base Employee Monthly Salary ($)", min_value=1.0, value=1500.0, step=100.0)
working_days_month = st.sidebar.number_input("Standard Working Days/Month", min_value=1, value=22, step=1)

# Math: 9 required hours per day = 540 minutes = 32,400 seconds
# Calculate rates down to the exact second
total_seconds_per_month = working_days_month * 9 * 60 * 60
per_second_rate = base_monthly_salary / total_seconds_per_month
per_minute_rate = per_second_rate * 60

st.sidebar.info(f"💡 **Calculated Rates:**\n* ${per_minute_rate:.4f} / minute\n* ${per_second_rate:.6f} / second")

## 📁 File Upload
uploaded_file = st.file_uploader("Upload Employee Sheet (e.g., Aashir.xls)", type=["xls", "xlsx"])

if uploaded_file is not None:
    try:
        df = pd.read_excel(uploaded_file, engine='xlrd')
        df['Original_DateTime'] = pd.to_datetime(df['Date/Time'])
        emp_name = df['Name'].iloc[0] if 'Name' in df.columns else "Employee"
        
        ## 🌙 Cross-Midnight / Night Shift Correction Logic
        # If a punch happens between 12:00 AM and 6:00 AM, it belongs to the previous day's work session
        def get_adjusted_work_date(dt):
            if 0 <= dt.hour < 6:
                return (dt - timedelta(days=1)).date()
            return dt.date()
            
        df['Work_Date'] = df['Original_DateTime'].apply(get_adjusted_work_date)
        
        # Aggregate Daily Punches based on the shifted Work Date
        summary = df.groupby(['Work_Date']).agg(
            Check_In=('Original_DateTime', 'min'),
            Check_Out=('Original_DateTime', 'max'),
            Punches=('Original_DateTime', 'count')
        ).reset_index()
        
        # Calculate precise total seconds worked
        summary['Total_Seconds'] = (summary['Check_Out'] - summary['Check_In']).dt.total_seconds()
        
        ## 🧠 Process Rules Engine
        def calculate_metrics(row):
            check_in_time = row['Check_In'].time()
            total_secs = row['Total_Seconds']
            
            # Determine Late Status (Shift start: 11 AM, Late Threshold: 12 PM)
            if check_in_time > time(12, 0):
                status = "⚠️ Late"
            elif check_in_time > time(11, 0):
                status = "⏱️ Grace Period"
            else:
                status = "✅ On Time"
                
            if row['Punches'] == 1:
                return "❌ Missing Punch Out", 0, 0, 0
            
            # Required Shift Duration: 9 Hours = 32,400 seconds
            required_secs = 9 * 60 * 60
            overtime_secs = max(0.0, total_secs - required_secs)
            shortage_secs = max(0.0, required_secs - total_secs)
            
            return status, total_secs, overtime_secs, shortage_secs

        # Apply Rules Engine
        res = summary.apply(calculate_metrics, axis=1)
        summary['Status'] = [r[0] for r in res]
        summary['Seconds_Worked'] = [r[1] for r in res]
        summary['Overtime_Secs'] = [r[2] for r in res]
        summary['Shortage_Secs'] = [r[3] for r in res]
        
        # Calculate Financial Impacts strictly per second
        summary['Deduction'] = summary['Shortage_Secs'] * per_second_rate
        summary['Overtime_Pay'] = summary['Overtime_Secs'] * per_second_rate 
        
        ## 📊 Management Metrics Overview
        st.subheader(f"📈 Performance Analysis: {emp_name}")
        c1, c2, c3, c4 = st.columns(4)
        
        total_overtime_mins = summary['Overtime_Secs'].sum() / 60
        total_shortage_mins = summary['Shortage_Secs'].sum() / 60
        net_deductions = summary['Deduction'].sum()
        net_overtime_pay = summary['Overtime_Pay'].sum()
        
        c1.metric("Total Overtime Logged", f"{total_overtime_mins:.1f} mins", f"+${net_overtime_pay:.2f}")
        c2.metric("Total Deficit Logged", f"{total_shortage_mins:.1f} mins", f"-${net_deductions:.2f}", delta_color="inverse")
        c3.metric("Late Days", len(summary[summary['Status'] == "⚠️ Late"]))
        c4.metric("Incomplete Logs", len(summary[summary['Status'] == "❌ Missing Punch Out"]))
        
        st.write("---")
        
        ## 🗂️ View Tabbing
        tab_ledger, tab_overtime, tab_deductions = st.tabs(["📋 Master Ledger", "🚀 Overtime Tracker", "💸 Deductions List"])
        
        # Helper formatting function
        def format_seconds(secs):
            if secs <= 0: return "N/A"
            h = int(secs // 3600)
            m = int((secs % 3600) // 60)
            s = int(secs % 60)
            return f"{h}h {m}m {s}s"

        with tab_ledger:
            master_display = pd.DataFrame({
                "Work Date": summary['Work_Date'].apply(lambda x: x.strftime('%b %d, %Y')),
                "Actual Check-In": summary['Check_In'].dt.strftime('%b %d, %I:%M:%S %p'),
                "Actual Check-Out": summary['Check_Out'].dt.strftime('%b %d, %I:%M:%S %p'),
                "Total Duration": summary['Seconds_Worked'].apply(format_seconds),
                "Status": summary['Status']
            })
            st.dataframe(master_display, use_container_width=True, hide_index=True)
            
        with tab_overtime:
            ot_df = summary[summary['Overtime_Secs'] > 0]
            if not ot_df.empty:
                st.dataframe(pd.DataFrame({
                    "Work Date": ot_df['Work_Date'].apply(lambda x: x.strftime('%b %d, %Y')),
                    "Overtime Duration": ot_df['Overtime_Secs'].apply(format_seconds),
                    "Accrued Earnings": ot_df['Overtime_Pay'].apply(lambda x: f"${x:.2f}")
                }), use_container_width=True, hide_index=True)
            else:
                st.success("No overtime recorded for this period.")
                
        with tab_deductions:
            deduct_df = summary[summary['Shortage_Secs'] > 0]
            if not deduct_df.empty:
                st.dataframe(pd.DataFrame({
                    "Work Date": deduct_df['Work_Date'].apply(lambda x: x.strftime('%b %d, %Y')),
                    "Deficit Duration": deduct_df['Shortage_Secs'].apply(format_seconds),
                    "Salary Deduction Penalty": deduct_df['Deduction'].apply(lambda x: f"-${x:.2f}")
                }), use_container_width=True, hide_index=True)
            else:
                st.success("Perfect attendance! Zero deductions calculated.")
        
        ## 📥 Export Section
        st.write("---")
        st.subheader("💾 Export Payroll Summary")
        
        export_df = summary.copy()
        export_df['Work_Date'] = export_df['Work_Date'].apply(lambda x: x.strftime('%Y-%m-%d'))
        export_df['Check_In'] = export_df['Check_In'].dt.strftime('%Y-%m-%d %H:%M:%S')
        export_df['Check_Out'] = export_df['Check_Out'].dt.strftime('%Y-%m-%d %H:%M:%S')
        export_df['Deduction'] = export_df['Deduction'].round(2)
        export_df['Overtime_Pay'] = export_df['Overtime_Pay'].round(2)
        
        csv_data = export_df[[
            'Work_Date', 'Check_In', 'Check_Out', 'Seconds_Worked', 
            'Overtime_Secs', 'Shortage_Secs', 'Deduction', 'Overtime_Pay', 'Status'
        ]].to_csv(index=False).encode('utf-8')
        
        st.download_button(
            label=f"📥 Download Precision Payroll Sheet for {emp_name}",
            data=csv_data,
            file_name=f"Precision_Payroll_{emp_name}_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )
                
    except Exception as e:
        st.error(f"Error compiling biometric parameters: {e}")
else:
    st.info("👋 Awaiting file upload from HR manager. Drop the Excel sheet here to run metrics.")
