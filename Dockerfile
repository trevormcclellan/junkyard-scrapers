# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application's code into the container at /app
COPY . .

# Copy the cron job file to the cron directory
COPY scrapers_cron /etc/cron.d/scrapers_cron

# Give execution rights on the cron job file
RUN chmod 0644 /etc/cron.d/scrapers_cron

# Create the log file to be able to run tail
RUN touch /var/log/cron.log

# Install cron
RUN apt-get update && apt-get install -y cron

# Copy the health check script
COPY healthcheck.sh /healthcheck.sh

# Give execution rights on the health check script
RUN chmod +x /healthcheck.sh

# Define the health check
HEALTHCHECK --interval=60s --timeout=10s --start-period=5s --retries=3 CMD /healthcheck.sh

# Run all scripts on container startup and start cron
CMD ["sh", "-c", "python /app/tearapart/main.py && python /app/utpap/main.py && python /app/pullnsave/main.py && cron && tail -f /var/log/cron.log"]
