import streamlit as st
import pandas as pd
from datetime import datetime, time, timedelta
import io

st.set_page_config(page_title="HR Payroll & Attendance Dashboard (PKR)", layout="wide")

## 🏢 Header
st.title("💼 HR Attendance & Payroll Processing Hub")
st.markdown("Upload raw biometric logs to compute shifts, lates, 8 PM partial overtime, and data-driven alternate Saturdays.")
st.write("---")

## ⚙️ Payroll Policy Settings
st.sidebar.header("⚙️ Payroll Configuration")
base_monthly_salary = st.sidebar.number_input("Base Employee Monthly Salary (PKR)", min_value=1.0, value=50000.0, step=1000.0)
working_days_month = st.sidebar.number_input("Standard Working Days/Month", min_value=1, value=30, step=1)

st.sidebar.write("---")
st.sidebar.header("🏝️ Paid Off-Days Adjustment")
approved_leaves = st.sidebar.number_input("Approved Paid Leaves Taken", min_value=0, value=0, step=1)
public_holidays = st.sidebar.number_input("Gazetted Public Holidays", min_value=0, value=0, step=1)

# Math calculations down to the exact second (9 hours per day rule)
total_expected_hours = working_days_month * 9
total_seconds_per_month = total_expected_hours * 60 * 60
per_second_rate = base_monthly_salary / total_seconds_per_month
per_minute_rate = per_second_rate * 60

st.sidebar.info(f"💡 **Calculated Rates (PKR):**\n* Expected Monthly Hours: {total_expected_hours} hrs\n* ₨ {per_minute_rate:.4f} / minute\n* ₨ {per_second_rate:.6f} / second")

## 📁 File Upload
uploaded_file = st.file_uploader("Upload Employee Sheet (e.g., Aashir.xls)", type=["xls", "xlsx"])

if uploaded_file is not None:
    try:
        df = pd.read_excel(uploaded_file, engine='xlrd')
        df['Original_DateTime'] = pd.to_datetime(df['Date/Time'])
        emp_name = df['Name'].iloc[0] if 'Name' in df.columns else "Employee"
        
        ## 🌙 Robust Night Shift Window (12-Hour Morning Grouping rule)
        def get_adjusted_work_date(dt):
            if 0 <= dt.hour < 12:
                return (dt - timedelta(days=1)).date()
            return dt.date()
            
        df['Work_Date'] = df['Original_DateTime'].apply(get_adjusted_work_date)
        
        # Build the dynamic date list from the entire month
        all_detected_dates = pd.date_range(start=df['Work_Date'].min(), end=df['Work_Date'].max()).date
        
        # Aggregate Daily Punches
        summary = df.groupby(['Work_Date']).agg(
            Check_In=('Original_DateTime', 'min'),
            Check_Out=('Original_DateTime', 'max'),
            Punches=('Original_DateTime', 'count')
        ).reindex(all_detected_dates).reset_index()
        
        summary.rename(columns={'index': 'Work_Date'}, inplace=True)
        summary['Punches'] = summary['Punches'].fillna(0).astype(int)
        
        # Smart Dynamic Weekend Resolver
        def evaluate_day_type(row):
            date_obj = row['Work_Date']
            if date_obj.weekday() == 6:
                return "Weekend"
            elif date_obj.weekday() == 5 and row['Punches'] == 0:
                return "Weekend"
            return "Working Day"
            
        summary['Day_Type'] = summary.apply(evaluate_day_type, axis=1)
        
        ## 🧠 Process Rules Engine
        def calculate_metrics(row):
            day_type = row['Day_Type']
            punches = row['Punches']
            
            if punches == 0:
                if day_type == "Weekend":
                    return "🎉 Weekend | 📋 Complete", 0.0, 0.0, 0.0
                else:
                    return "❌ Absent / Unpaid Day", 0.0, 9 * 60 * 60, 0.0
            
            check_in_dt = row['Check_In']
            check_out_dt = row['Check_Out']
            check_in_time = check_in_dt.time()
            
            if check_in_time > time(12, 0):
                time_status = "⚠️ Late"
            elif check_in_time > time(11, 0):
                time_status = "⏱️ Grace Period"
            else:
                time_status = "✅ On Time"
                
            if punches == 1:
                if day_type == "Weekend":
                    return "🎉 Weekend | 📋 Complete", 0.0, 0.0, 0.0
                return f"{time_status} | ❌ Missing Punch Out", 0.0, 9 * 60 * 60, 0.0

            # --- 🕗 The 8 PM Overtime Rule Engine ---
            eight_pm_cutoff = datetime.combine(check_in_dt.date() + timedelta(days=1) if check_in_dt.hour >= 12 and check_out_dt.hour < 12 else check_in_dt.date(), time(20, 0, 0))
            if check_out_dt.hour < 12 and check_in_dt.hour >= 12:
                eight_pm_cutoff = datetime.combine(check_in_dt.date(), time(20, 0, 0))
            
            overtime_secs = 0.0
            if check_out_dt > eight_pm_cutoff:
                overtime_secs = max(0.0, (check_out_dt - eight_pm_cutoff).total_seconds())
                effective_checkout = eight_pm_cutoff
            else:
                effective_checkout = check_out_dt
                
            standard_worked_secs = max(0.0, (effective_checkout - check_in_dt).total_seconds())
            required_secs = 9 * 60 * 60
            shortage_secs = max(0.0, required_secs - standard_worked_secs)
            
            if day_type == "Weekend":
                return "🎉 Weekend | 📋 Complete", (check_out_dt - check_in_dt).total_seconds(), 0.0, 0.0

            final_status = f"{time_status} | 📋 Complete"
            if overtime_secs > 0:
                final_status += " + 🚀 Post-8PM OT"
                
            return final_status, (check_out_dt - check_in_dt).total_seconds(), shortage_secs, overtime_secs

        res = summary.apply(calculate_metrics, axis=1)
        summary['Combined_Status'] = [r[0] for r in res]
        summary['Seconds_Worked'] = [r[1] for r in res]
        summary['Shortage_Secs'] = [r[2] for r in res]
        summary['Overtime_Secs'] = [r[3] for r in res]
        
        summary['Deduction'] = summary['Shortage_Secs'] * per_second_rate
        summary['Overtime_Pay'] = summary['Overtime_Secs'] * (per_second_rate * 0.5)
        
        ## 📊 Management Metrics Overview
        st.subheader(f"📈 Performance Analysis: {emp_name}")
        c1, c2, c3, c4 = st.columns(4)
        
        total_shortage_mins = summary['Shortage_Secs'].sum() / 60
        total_ot_mins = summary['Overtime_Secs'].sum() / 60
        net_deductions = summary['Deduction'].sum()
        net_ot_payout = summary['Overtime_Pay'].sum()
        
        leave_credit_pkr = (approved_leaves + public_holidays) * (9 * 60 * 60 * per_second_rate)
        adjusted_deductions = max(0.0, net_deductions - leave_credit_pkr)
        
        c1.metric("Total Attendance Deficit", f"{total_shortage_mins:.1f} mins", f"-₨ {net_deductions:,.2f}", delta_color="inverse")
        c2.metric("Post-8PM Overtime (Half-Pay)", f"{total_ot_mins:.1f} mins", f"+₨ {net_ot_payout:,.2f}")
        c3.metric("Late Day Flags", len(summary[summary['Combined_Status'].str.contains("⚠️ Late")]))
        c4.metric("Expected Tracked Hours", f"{total_expected_hours} Hrs")
        
        ## 💵 FINAL SALARY PAYOUT STATEMENT SECTION
        st.write("---")
        st.subheader("💵 Monthly Payroll Payout Statement")
        
        final_take_home = base_monthly_salary - adjusted_deductions + net_ot_payout
        
        sc1, sc2, sc3, sc4 = st.columns(4)
        sc1.markdown(f"**Gross Base Salary:**\n### ₨ {base_monthly_salary:,.2f}")
        sc2.markdown(f"**(+) Compensatory Overtime:**\n### <span style='color:green;'>₨ {net_ot_payout:,.2f}</span>", unsafe_allow_html=True)
        sc3.markdown(f"**(-) Net Attendance Deductions:**\n### <span style='color:red;'>₨ {adjusted_deductions:,.2f}</span>", unsafe_allow_html=True)
        sc4.markdown(f"**💰 Net Disbursable Salary:**\n## ₨ {final_take_home:,.2f}")
        
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
                "Work Date": summary['Work_Date'].apply(lambda x: x.strftime('%b %d, %Y') if not pd.isnull(x) else ''),
                "Actual Check-In": summary['Check_In'].apply(lambda x: x.strftime('%b %d, %I:%M:%S %p') if not pd.isnull(x) else 'N/A'),
                "Actual Check-Out": summary['Check_Out'].apply(lambda x: x.strftime('%b %d, %I:%M:%S %p') if not pd.isnull(x) else 'N/A'),
                "Total Duration": summary['Seconds_Worked'].apply(format_seconds),
                "Post-8PM Overtime": summary['Overtime_Secs'].apply(format_seconds),
                "Status Details": summary['Combined_Status']
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
            'Check In': summary['Check_In'].apply(lambda x: x.strftime('%H:%M:%S') if not pd.isnull(x) else 'N/A'),
            'Check Out': summary['Check_Out'].apply(lambda x: x.strftime('%H:%M:%S') if not pd.isnull(x) else 'N/A'),
            'Total Worked': summary['Seconds_Worked'].apply(format_seconds),
            'Deficit Shortage': summary['Shortage_Secs'].apply(format_seconds),
            'Post-8PM OT Duration': summary['Overtime_Secs'].apply(format_seconds),
            'Deductions (PKR)': summary['Deduction'],
            'Overtime Pay (PKR)': summary['Overtime_Pay'],
            'Status Flags': summary['Combined_Status']
        })
        
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            output_df.to_excel(writer, sheet_name='Payroll Summary', index=False)
            
            workbook  = writer.book
            worksheet = writer.sheets['Payroll Summary']
            
            # Formatting configurations
            currency_format = workbook.add_format({'num_format': '₨ #,##0.00', 'align': 'right'})
            red_currency_format = workbook.add_format({'num_format': '₨ #,##0.00', 'font_color': 'red', 'align': 'right'})
            bold_red_currency_format = workbook.add_format({'bold': True, 'num_format': '₨ #,##0.00', 'font_color': 'red', 'align': 'right'})
            
            bold_format = workbook.add_format({'bold': True})
            bold_currency_format = workbook.add_format({'bold': True, 'num_format': '₨ #,##0.00', 'align': 'right'})
            
            total_label_format = workbook.add_format({'bold': True, 'align': 'right', 'top': 1})
            total_value_format = workbook.add_format({'bold': True, 'num_format': '₨ #,##0.00', 'top': 1, 'align': 'right'})
            total_value_red_format = workbook.add_format({'bold': True, 'num_format': '₨ #,##0.00', 'font_color': 'red', 'top': 1, 'align': 'right'})
            
            worksheet.set_column('A:F', 15)
            worksheet.set_column('G:G', 22, red_currency_format) # Set the regular deductions column text to Red
            worksheet.set_column('H:H', 22, currency_format)
            worksheet.set_column('I:I', 35)
            
            last_row = len(output_df) + 1
            worksheet.write(last_row, 5, 'Total Adjustments Summary:', total_label_format)
            worksheet.write_formula(last_row, 6, f'=SUM(G2:G{last_row})', total_value_red_format)
            worksheet.write_formula(last_row, 7, f'=SUM(H2:H{last_row})', total_value_format)
            
            # Bottom Invoice Summary Statement Panel
            statement_start_row = last_row + 3
            worksheet.write(statement_start_row, 5, 'Payroll Summary Payout Statement', bold_format)
            
            worksheet.write(statement_start_row + 1, 5, 'Total Expected Monthly Work Hours:')
            worksheet.write(statement_start_row + 1, 6, f"{total_expected_hours} Hours", bold_format)
            
            worksheet.write(statement_start_row + 2, 5, 'Gross Base Salary:')
            worksheet.write(statement_start_row + 2, 6, base_monthly_salary, currency_format)
            
            worksheet.write(statement_start_row + 3, 5, 'Compensatory Overtime Earned (+):')
            worksheet.write_formula(statement_start_row + 3, 6, f'=H{last_row+1}', currency_format)
            
            worksheet.write(statement_start_row + 4, 5, 'Attendance Penalty Deductions (-):')
            worksheet.write_formula(statement_start_row + 4, 6, f'=MAX(0, G{last_row+1} - ({approved_leaves + public_holidays}*32400*{per_second_rate:.8f}))', bold_red_currency_format)
            
            worksheet.write(statement_start_row + 5, 5, 'Net Take-Home Salary (PKR):', total_label_format)
            worksheet.write_formula(statement_start_row + 5, 6, f'=(G{statement_start_row + 3}+G{statement_start_row + 4})-G{statement_start_row + 5}', bold_currency_format)
            
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
