from docx import Document
import sys

doc = Document(r'C:\Users\Administrator\Desktop\智能文档检索助手\agent.docx')
for para in doc.paragraphs:
    if para.text.strip():
        print(para.text)
