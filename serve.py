import os
import time
import csv
import numpy as np
import matplotlib.pyplot as plt
from flask import Flask, send_file, render_template, jsonify
import subprocess
from simple_pid import PID

app = Flask(__name__)

# Fan control options
TEMPERATURE_TARGET = 50  # Target temperature in Celsius
FAN_SPEED_MIN = 40  # Minimum fan speed in %
fan_pid = [PID(2, 0.01, 0.15, setpoint=TEMPERATURE_TARGET) for _ in range(2)]
fan_speed = [0] * 2
adjusted_fan_speed = [0] * 2

# Plotting options
PLOT_LATEST_N = 30
DATA_FILE = "gpu_temperatures.csv"

def get_nvidia_smi_output():
    """Fetches the output of the nvidia-smi command."""
    try:
        output = subprocess.check_output(["nvidia-smi"], encoding='utf-8')
        return output
    except subprocess.CalledProcessError as e:
        return f"Error fetching nvidia-smi output: {e}"

def get_gpus_temp():
    """Fetches the maximum GPU temperature using nvidia-smi."""
    gpu_temps = subprocess.check_output(
        ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"]
    ).decode("utf-8").strip().split("\n")
    return list(map(int, gpu_temps))

def plot_data():
    """Generates a plot of the logged GPU temperatures."""
    if not os.path.exists(DATA_FILE):
        return None

    # Read GPU temperatures
    timestamps = []
    gpu_1_temperature = []
    gpu_2_temperature = []
    fan_1_speed = []
    fan_2_speed = []
    with open(DATA_FILE, mode='r') as file:
        reader = csv.reader(file)
        for row in reader:
            timestamps.append(row[0])
            gpu_1_temperature.append(int(row[1]))
            gpu_2_temperature.append(int(row[2]))
            fan_1_speed.append(float(row[3]))
            fan_2_speed.append(float(row[4]))

    timestamps = timestamps[-PLOT_LATEST_N:]
    gpu_1_temperature = gpu_1_temperature[-PLOT_LATEST_N:]
    gpu_2_temperature = gpu_2_temperature[-PLOT_LATEST_N:]
    fan_1_speed = fan_1_speed[-PLOT_LATEST_N:]
    fan_2_speed = fan_2_speed[-PLOT_LATEST_N:]

    # Create a figure with two subplots side by side
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 5), sharey=False)

    # Plot for GPU 1
    ax1_temperature = ax1
    ax1_fan = ax1.twinx()
    ax1_temperature.plot(timestamps, gpu_1_temperature, marker='o', color='green', label='GPU 1 Temperature (°C)')
    ax1_fan.plot(timestamps, fan_1_speed, marker='x', color='red', label='Fan 1 Speed')
    ax1_temperature.axhline(y=TEMPERATURE_TARGET, color='g', linestyle='--', label=f"Target Temperature ({TEMPERATURE_TARGET}°C)")
    ax1_temperature.set_title("GPU 1")
    ax1_temperature.set_xlabel('Timestamp')
    ax1_temperature.set_ylabel('Temperature (°C)', color='green')
    ax1_fan.set_ylabel('Fan Speed', color='red')
    ax1_temperature.tick_params(axis='y', labelcolor='green')
    ax1_fan.tick_params(axis='y', labelcolor='orange')
    ax1_temperature.legend(loc='upper left')
    ax1_fan.legend(loc='upper right')
    ax1_temperature.grid(True)
    ax1_temperature.set_ylim(0, 100)  # Set y-axis limits to between 0 and 100
    ax1_fan.set_ylim(0, 100)  # Set y-axis limits to between 0 and 100

    # Plot for GPU 2
    ax2_temperature = ax2
    ax2_fan = ax2.twinx()
    ax2_temperature.plot(timestamps, gpu_2_temperature, marker='o', color='green', label='GPU 2 Temperature (°C)')
    ax2_fan.plot(timestamps, fan_2_speed, marker='x', color='red', label='Fan 2 Speed')
    ax2_temperature.axhline(y=TEMPERATURE_TARGET, color='g', linestyle='--', label=f"Target Temperature ({TEMPERATURE_TARGET}°C)")
    ax2_temperature.set_title("GPU 2")
    ax2_temperature.set_xlabel('Timestamp')
    ax2_temperature.set_ylabel('Temperature (°C)', color='green')
    ax2_fan.set_ylabel('Fan Speed', color='red')
    ax2_temperature.tick_params(axis='y', labelcolor='green')
    ax2_fan.tick_params(axis='y', labelcolor='red')
    ax2_temperature.legend(loc='upper left')
    ax2_fan.legend(loc='upper right')
    ax2_temperature.grid(True)
    ax2_temperature.set_ylim(0, 100)  # Set y-axis limits to between 0 and 100
    ax2_fan.set_ylim(0, 100)  # Set y-axis limits to between 0 and 100

    # Save the plot as a JPEG file
    plot_file = "gpu_temperatures_side_by_side.jpg"
    plt.savefig(plot_file)
    plt.close()
    return plot_file

@app.route('/')
def index():
    """Displays the plot and nvidia-smi output on the web page with modern styling."""
    nvidia_output = get_nvidia_smi_output()
    return render_template("index.html", nvidia_output=nvidia_output, gpu_temperature=get_gpus_temp(), fan_speed=fan_speed, adjusted_fan_speed=adjusted_fan_speed)

@app.route('/fan_control')
def fan_control():
    """Control the fan speed."""
    # Get temperature for cards.
    output = subprocess.check_output(['nvidia-smi', '-q'])
    lines = output.decode().split('\n')
    gpus_temp = [float(line.split(':')[1][:-2]) for line in lines if 'GPU Current Temp' in line]

    # Update fan speed
    fan_speed_delta = [pid_and_temp[0](pid_and_temp[1]) for pid_and_temp in zip(fan_pid, gpus_temp)]

    for i in range(2):
        # We do minus because increasing the control decreases speed.
        fan_speed[i] = min(max(FAN_SPEED_MIN, fan_speed[i] - 0.1 * fan_speed_delta[i]), 100.0)
        adjusted_fan_speed[i] = 0 if fan_speed[i] < FAN_SPEED_MIN + 0.5 else fan_speed[i]
    return jsonify({'gpu_temps': gpus_temp, 'fan_speed': adjusted_fan_speed, 'fan_speed_before_adjustment': fan_speed, 'fan_speed_delta': fan_speed_delta})

@app.route('/plot')
def plot():
    """Serves the temperature plot as an image."""
    plot_file = plot_data()
    if plot_file:
        return send_file(plot_file, mimetype='image/jpeg')
    return "No temperature data available."

if __name__ == "__main__":
    # Start a separate thread to log the temperature and USB state every minute
    import threading
    
    def log_data_periodically():
        while True:
            temps = get_gpus_temp()
            with open(DATA_FILE, mode='a', newline='') as file:
                writer = csv.writer(file)
                writer.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), temps[0], temps[1], adjusted_fan_speed[0], adjusted_fan_speed[1]])
            print(f"Logged temperature: {temps}°C")
            print(f"Logged adjusted_fan_speed: {adjusted_fan_speed}°C")
            time.sleep(10)  # Log every minute

    threading.Thread(target=log_data_periodically, daemon=True).start()
    
    # Run the Flask app
    app.run(host='0.0.0.0', port=5000)
