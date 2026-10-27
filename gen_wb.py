import base64

with open('data/AI_Engineer_Leave_Management_Dataset.xlsx', 'rb') as f:
    b = f.read()

s = base64.b64encode(b).decode()

with open('backend/app/workbook_data.py', 'w', encoding='utf-8') as out:
    out.write("WORKBOOK_B64 = '''" + s + "'''\n")
