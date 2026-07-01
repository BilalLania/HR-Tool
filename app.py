import streamlit as st
import pandas as pd
from datetime import datetime, time, timedelta
import io

st.set_page_config(page_title="HR Payroll & Attendance Dashboard (PKR)", layout="wide")

## 🏢 Header
st.title("💼 HR Attendance & Payroll Processing Hub")
st.markdown("Upload raw biometric logs to compute shifts, cross-midnight logs, and exact per-second salary adjustments.")
st.write("---")

## ⚙️ Payroll Policy Settings
st.sidebar.header("⚙️ Payroll Configuration")
base_monthly_salary = st.sidebar.number_input("Base Employee Monthly Salary (PKR)", min_value=1.0, value=50000.0, step=1000.0)
working_days_month = st.sidebar.number_input("Standard Working Days/Month", min_value=1, value=30, step=1)

# Math calculations down to the exact second (9 hours per day rule)
total_seconds_per_month = working_days_month * 9 * 60 * 60
per_second_rate = base_monthly_salary / total_seconds_per_month
per_minute_rate = per_second_rate * 60

st.sidebar.info(f"💡 **Calculated Rates (PKR):**\n* ₨ {per_minute_rate:.4f} / minute\n* ₨ {per_second_rate:.6f} / second")

## 📁 File Upload
uploaded_file = st.file_uploader("Upload Employee Sheet (e.g., Aashir.xls)", type=["xls", "xlsx"])

if uploaded_file is not None:
    try:
        df = pd.read_excel(uploaded_file, engine='xlrd')
        df['Original_DateTime'] = pd.to_datetime(df['Date/Time'])
        emp_name = df['Name'].iloc[0] if 'Name' in df.columns else "Employee"
        
        ## 🌙 Cross-Midnight / Night Shift Correction Logic
        def get_adjusted_work_date(dt):
            if 0 <= dt.hour < 6:
                return (dt - timedelta(days=1)).date()
            return dt.date()
            
        df['Work_Date'] = df['Original_DateTime'].apply(get_adjusted_work_date)
        
        # Aggregate Daily Punches
        summary = df.groupby(['Work_Date']).agg(
            Check_In=('Original_DateTime', 'min'),
            Check_Out=('Original_DateTime', 'max'),
            Punches=('Original_DateTime', 'count')
        ).reset_index()
        
        summary['Total_Seconds'] = (summary['Check_Out'] - summary['Check_In']).dt.total_seconds()
        
        ## 🧠 Process Rules Engine
        def calculate_metrics(row):
            check_in_time = row['Check_In'].time()
            total_secs = row['Total_Seconds']
            
            if check_in_time > time(12, 0):
                status = "⚠️ Late"
            elif check_in_time > time(11, 0):
                status = "⏱️ Grace Period"
            else:
                status = "✅ On Time"
                
            if row['Punches'] == 1:
                return "❌ Missing Punch Out", 0, 0
            
            required_secs = 9 * 60 * 60
            shortage_secs = max(0.0, required_secs - total_secs)
            
            return status, total_secs, shortage_secs

        res = summary.apply(calculate_metrics, axis=1)
        summary['Status'] = [r[0] for r in res]
        summary['Seconds_Worked'] = [r[1] for r in res]
        summary['Shortage_Secs'] = [r[2] for r in res]
        
        summary['Deduction'] = summary['Shortage_Secs'] * per_second_rate
        
        ## 📊 Management Metrics Overview
        st.subheader(f"📈 Performance Analysis: {emp_name}")
        c1, c2, c3 = st.columns(3)
        
        total_shortage_mins = summary['Shortage_Secs'].sum() / 60
        net_deductions = summary['Deduction'].sum()
        
        c1.metric("Total Deficit Logged", f"{total_shortage_mins:.1f} mins", f"-₨ {net_deductions:,.2f}", delta_color="inverse")
        c2.metric("Late Days", len(summary[summary['Status'] == "⚠️ Late"]))
        c3.metric("Incomplete Logs", len(summary[summary['Status'] == "❌ Missing Punch Out"]))
        
        ## 💵 FINAL SALARY PAYOUT STATEMENT SECTION
        st.write("---")
        st.subheader("💵 Monthly Payroll Payout Statement")
        
        final_take_home = base_monthly_salary - net_deductions
        
        sc1, sc2, sc3 = st.columns(3)
        sc1.markdown(f"**Gross Base Salary:**\n### ₨ {base_monthly_salary:,.2f}")
        sc2.markdown(f"**(-) Attendance Deductions:**\n### <span style='color:red;'>₨ {net_deductions:,.2f}</span>", unsafe_allow_html=True)
        sc3.markdown(f"**💰 Net Disbursable Salary:**\n## ₨ {final_take_home:,.2f}")
        
        st.write("---")
        
        ## 🗂️ View Tabbing
        tab_ledger, tab_deductions = st.tabs(["📋 Master Ledger", "💸 Deductions List"])
        
        def format_seconds(secs):
            if secs <= 0: return "00:00:00"
            h = int(secs // 3600)
            m = int((secs % 3600) // 60)
            s = int(secs % 60)
            return f"{h:02d}:{m:02d}:{s:02d}"

        with tab_ledger:
            master_display = pd.DataFrame({
                "Work Date": summary['Work_Date'].apply(lambda x: x.strftime('%b %d, %Y')),
                "Actual Check-In": summary['Check_In'].dt.strftime('%b %d, %I:%M:%S %p'),
                "Actual Check-Out": summary['Check_Out'].dt.strftime('%b %d, %I:%M:%S %p'),
                "Total Duration": summary['Seconds_Worked'].apply(format_seconds),
                "Status": summary['Status']
            })
            st.dataframe(master_display, use_container_width=True, hide_index=True)
            
        with tab_deductions:
            deduct_df = summary[summary['Shortage_Secs'] > 0]
            if not deduct_df.empty:
                st.dataframe(pd.DataFrame({
                    "Work Date": deduct_df['Work_Date'].apply(lambda x: x.strftime('%b %d, %Y')),
                    "Deficit Duration": deduct_df['Shortage_Secs'].apply(format_seconds),
                    "Salary Deduction Penalty": deduct_df['Deduction'].apply(lambda x: f"-₨ {x:,.2f}")
                }), use_container_width=True, hide_index=True)
            else:
                st.success("Perfect attendance! Zero deductions calculated.")
        
        ## 📥 Advanced Excel Generation Engine
        st.write("---")
        st.subheader("💾 Export Clean Payroll Record")
        
        output_df = pd.DataFrame({
            'Work Date': summary['Work_Date'].apply(lambda x: x.strftime('%Y-%m-%d')),
            'Check In': summary['Check_In'].dt.strftime('%H:%M:%S'),
            'Check Out': summary['Check_Out'].dt.strftime('%H:%M:%S'),
            'Total Worked': summary['Seconds_Worked'].apply(format_seconds),
            'Shortage Total': summary['Shortage_Secs'].apply(format_seconds),
            'Deductions (PKR)': summary['Deduction'],
            'Status': summary['Status']
        })
        
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            output_df.to_excel(writer, sheet_name='Payroll Summary', index=False)
            
            workbook  = writer.book
            worksheet = writer.sheets['Payroll Summary']
            
            # Text formatting
            currency_format = workbook.add_format({'num_format': '₨ #,##0.00', 'align': 'right'})
            bold_format = workbook.add_format({'bold': True})
            bold_currency_format = workbook.add_format({'bold': True, 'num_format': '₨ #,##0.00', 'align': 'right'})
            
            total_label_format = workbook.add_format({'bold': True, 'align': 'right', 'top': 1})
            total_value_format = workbook.add_format({'bold': True, 'num_format': '₨ #,##0.00', 'top': 1, 'align': 'right'})
            
            worksheet.set_column('A:E', 15)
            worksheet.set_column('F:F', 22, currency_format)
            worksheet.set_column('G:G', 18)
            
            # Add dynamic SUM row below data ledger
            data_end_row = len(output_df) + 1
            worksheet.write(data_end_row, 4, 'Total Deductions:', total_label_format)
            worksheet.write_formula(data_end_row, 5, f'=SUM(F2:F{data_end_row})', total_value_format)
            
            # Create a separate block section at the bottom for final take-home breakdown
            statement_start_row = data_end_row + 3
            worksheet.write(statement_start_row, 4, 'Payroll Summary Payout Statement', bold_format)
            
            worksheet.write(statement_start_row + 1, 4, 'Gross Base Salary:')
            worksheet.write(statement_start_row + 1, 5, base_monthly_salary, currency_format)
            
            worksheet.write(statement_start_row + 2, 4, 'Total Deductions Penalty:')
            worksheet.write_formula(statement_start_row + 2, 5, f'=F{data_end_row+1}', currency_format)
            
            worksheet.write(statement_start_row + 3, 4, 'Net Take-Home Salary (PKR):', total_label_format)
            worksheet.write_formula(statement_start_row + 3, 5, f'=F{statement_start_row + 2}-F{statement_start_row + 3}', bold_currency_format)
            
        excel_data = buffer.getvalue()
        
        st.download_button(
            label=f"📥 Download Structured Excel Sheet for {emp_name}",
            data=excel_data,
            file_name=f"Precision_Payroll_Final_{emp_name}_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
                
    except Exception as e:
        st.error(f"Error compiling biometric parameters: {e}")
else:
    st.info("👋 Awaiting file upload from HR manager. Drop the Excel sheet here to run metrics.")
