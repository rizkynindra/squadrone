FROM python:3.11-slim

# Set the working directory
WORKDIR /app

# Install system dependencies (Windows compatible base image does not need these Linux packages)

# Copy the requirements file and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application files
COPY . .

# Set the environment variable for Streamlit
# ENV STREAMLIT_SERVER_HEADLESS true

# Expose Streamlit default port
EXPOSE 8501

# Run the Streamlit app
CMD ["streamlit", "run", "app.py"]
