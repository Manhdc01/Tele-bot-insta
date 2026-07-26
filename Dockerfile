FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ĐẢM BẢO CÓ DÒNG NÀY ĐỂ TẢI BROWSER CHROMIUM CHO PLAYWRIGHT
RUN python -m playwright install chromium --with-deps

COPY . .

CMD ["python", "main.py"]