FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy compressed demo data and extract
COPY data/csv-demo.tar.gz /app/data/
RUN cd /app/data && tar xzf csv-demo.tar.gz && mv demo "Inventory Management" && rm csv-demo.tar.gz

# Copy trained models
COPY data/models/ /app/data/models/

# Copy source code
COPY src/ /app/src/
COPY run.py /app/

ENV DATA_PATH=/app/data/Inventory\ Management
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

EXPOSE 8080

CMD ["python", "run.py"]
