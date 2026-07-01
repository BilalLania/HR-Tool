import streamlit as st
import pandas as pd
from datetime import datetime, time

st.set_page_config(page_title="HR Payroll & Attendance Dashboard", layout="wide")

## 🏢 Header
st.title("💼 HR Attendance & Payroll Processing Hub")
st.markdown("Upload raw biometric logs to compute shifts, overtime, and exact per-minute salary adjustments.")
st.write("---")

## ⚙️ Payroll Policy Settings
st.sidebar.header("⚙️ Payroll Configuration")
base_monthly_salary = st.sidebar.number_input("Base Employee Monthly Salary ($)", min_value=1, value=1500, step=100)
working_days_month = st.sidebar.number_input("Standard Working Days/Month", min_value=1, value=22, step=1)

# Math: Calculate per-minute rate based on 9 required hours per day
# Total minutes per month = working days * 9 hours * 60 minutes
total_minutes_per_month = working_days_month * 9 * 60
per_minute_rate = base_monthly_salary / total_minutes_per_month

st.sidebar.info(f"💡 **Calculated Rate:** ${per_minute_rate:.4f} per minute worked.")

## 📁 File Upload
uploaded_file = st.file_uploader("Upload Employee Sheet (e.g., Aashir.xls)", type=["xls", "xlsx"])

if uploaded_file is not None:
    try:
        df = pd.read_excel(uploaded_file, engine='xlrd')
        df['Date/Time'] = pd.to_datetime(df['Date/Time'])
        df['Date'] = df['Date/Time'].dt.date
        emp_name = df['Name'].iloc[0] if 'Name' in df.columns else "Employee"
        
        # Aggregate Daily Punches
        summary = df.groupby(['Date']).agg(
            Check_In=('Date/Time', 'min'),
            Check_Out=('Date/Time', 'max'),
            Punches=('Date/Time', 'count')
        ).reset_index()
        
        # Calculate minutes worked
        summary['Total_Minutes'] = (summary['Check_Out'] - summary['Check_In']).dt.total_seconds() / 60
        
        ## 🧠 Process Rules Engine
        def calculate_metrics(row):
            check_in_time = row['Check_In'].time()
            total_mins = row['Total_Minutes']
            
            # 1. Determine Late Status (Shift start: 11 AM, Late: 12 PM)
            if check_in_time > time(12, 0):
                status = "⚠️ Late"
            elif check_in_time > time(11, 0):
                status = "⏱️ Grace Period"
            else:
                status = "✅ On Time"
                
            if row['Punches'] == 1:
                return "❌ Missing Punch Out", 0, 0, 0
            
            # 2. Overtime vs Shortage Math (9 Hours = 540 minutes)
            required_mins = 540
            overtime_mins = max(0, total_mins - required_mins)
            shortage_mins = max(0, required_mins - total_mins)
            
            return status, total_mins, overtime_mins, shortage_mins

        # Apply Rules Engine
        res = summary.apply(calculate_metrics, axis=1)
        summary['Status'] = [r[0] for r in res]
        summary['Minutes_Worked'] = [r[1] for r in res]
        summary['Overtime_Mins'] = [r[2] for r in res]
        summary['Shortage_Mins'] = [r[3] for r in res]
        
        # Calculate Financial Impacts
        summary['Deduction'] = summary['Shortage_Mins'] * per_minute_rate
        summary['Overtime_Pay'] = summary['Overtime_Mins'] * per_minute_rate 
        
        ## 📊 Management Metrics Overview
        st.subheader(f"📈 Performance Analysis: {emp_name}")
        c1, c2, c3, c4 = st.columns(4)
        
        total_overtime = summary['Overtime_Mins'].sum()
        total_shortage = summary['Shortage_Mins'].sum()
        net_deductions = summary['Deduction'].sum()
        net_overtime_pay = summary['Overtime_Pay'].sum()
        
        c1.metric("Total Overtime Logged", f"{total_overtime:.0f} mins", f"+${net_overtime_pay:.2f}")
        c2.metric("Total Deficit Logged", f"{total_shortage:.0f} mins", f"-${net_deductions:.2f}", delta_color="inverse")
        c3.metric("Late Days", len(summary[summary['Status'] == "⚠️ Late"]))
        c4.metric("Incomplete Logs", len(summary[summary['Status'] == "❌ Missing Punch Out"]))
        
        st.write("---")
        
        ## 🗂️ View Tabbing
        tab_ledger, tab_overtime, tab_deductions = st.tabs(["📋 Master Ledger", "🚀 Overtime Tracker", "💸 Deductions List"])
        
        with tab_ledger:
            master_display = pd.DataFrame({
                "Date": summary['Date'],
                "In Time": summary['Check_In'].dt.strftime('%I:%M %p'),
                "Out Time": summary['Check_Out'].dt.strftime('%I:%M %p'),
                "Total Duration": (summary['Minutes_Worked'] / 60).apply(lambda x: f"{x:.2f} hrs" if x > 0 else "N/A"),
                "Status": summary['Status']
            })
            st.dataframe(master_display, use_container_width=True, hide_index=True)
            
        with tab_overtime:
            ot_df = summary[summary['Overtime_Mins'] > 0]
            if not ot_df.empty:
                st.dataframe(pd.DataFrame({
                    "Date": ot_df['Date'],
                    "Overtime Duration": ot_df['Overtime_Mins'].apply(lambda x: f"{x:.0f} mins ({x/60:.2f} hrs)"),
                    "Accrued Earnings": ot_df['Overtime_Pay'].apply(lambda x: f"${x:.2f}")
                }), use_container_width=True, hide_index=True)
            else:
                st.success("No overtime recorded for this period.")
                
        with tab_deductions:
            deduct_df = summary[summary['Shortage_Mins'] > 0]
            if not deduct_df.empty:
                st.dataframe(pd.DataFrame({
                    "Date": deduct_df['Date'],
                    "Deficit Minutes": deduct_df['Shortage_Mins'].apply(lambda x: f"{x:.0f} mins short"),
                    "Salary Deduction Penalty": deduct_df['Deduction'].apply(lambda x: f"-${x:.2f}")
                }), use_container_width=True, hide_index=True)
            else:
                st.success("Perfect attendance! Zero deductions calculated.")
        
        ## 📥 Export Section
        st.write("---")
        st.subheader("💾 Export Payroll Summary")
        
        # Format the master summary table neatly for the CSV export
        export_df = summary.copy()
        export_df['Date'] = pd.to_datetime(export_df['Date']).dt.strftime('%Y-%m-%d')
        export_df['Check_In'] = export_df['Check_In'].dt.strftime('%I:%M %p')
        export_df['Check_Out'] = export_df['Check_Out'].dt.strftime('%I:%M %p')
        export_df['Hours_Worked'] = (export_df['Minutes_Worked'] / 60).round(2)
        
        csv_data = export_df[[
            'Date', 'Check_In', 'Check_Out', 'Hours_Worked', 
            'Overtime_Mins', 'Shortage_Mins', 'Deduction', 'Overtime_Pay', 'Status'
        ]].to_csv(index=False).encode('utf-8')
        
        st.download_button(
            label=f"📥 Download Payroll Sheet for {emp_name}",
            data=csv_data,
            file_name=f"Payroll_Summary_{emp_name}_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )
                
    except Exception as e:
        st.error(f"Error compiling biometric parameters: {e}")
else:
    st.info("👋 Awaiting file upload from HR manager. Drop the Excel sheet here to run metrics.")