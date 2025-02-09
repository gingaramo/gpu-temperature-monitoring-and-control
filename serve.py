import os
import time
import csv
import numpy as np
import matplotlib.pyplot as plt
from flask import Flask, send_file, render_template, jsonify, request, redirect
import subprocess
import threading
from simple_pid import PID

app = Flask(__name__)

# Fan control constants
TEMPERATURE_TARGET = 50  # Target temperature in Celsius
FAN_SPEED_MIN = 40       # Minimum fan speed in percent

# Initialize PID controllers for two fans
fan_pid_controllers = [PID(1, 0.00, 0.05, setpoint=TEMPERATURE_TARGET) for _ in range(2)]
current_fan_speeds = [FAN_SPEED_MIN] * 2
adjusted_fan_speeds = [FAN_SPEED_MIN] * 2

# Plotting constants
NUM_POINTS_TO_PLOT = 30
DATA_LOG_FILE = "gpu_temperatures.csv"

def fetch_nvidia_smi_output():
    """Fetches the output of the nvidia-smi command."""
    try:
        return subprocess.check_output(["nvidia-smi"], encoding='utf-8')
    except subprocess.CalledProcessError as e:
        return f"Error fetching nvidia-smi output: {e}"

def fetch_ollama_ps_output():
    """Fetches the output of ollama ps command."""
    try:
        return subprocess.check_output(["ollama", "ps"], encoding='utf-8')
    except subprocess.CalledProcessError as e:
        return f"Error fetching ollama output: {e}"

def get_gpu_temperatures():
    """Fetches the maximum GPU temperatures using nvidia-smi."""
    try:
        temps = subprocess.check_output(
        ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"]
    ).decode("utf-8").strip().split("\n")
        return [int(temp) for temp in temps]
    except Exception as e:
        print(f"Error fetching GPU temperatures: {e}")
        return [0] * 2

def generate_temperature_plot():
    """Generates a plot of the logged GPU temperatures."""
    if not os.path.exists(DATA_LOG_FILE):
        return None

    timestamps = []
    gpu_1_temps = []
    gpu_2_temps = []
    fan_1_speeds = []
    fan_2_speeds = []
    with open(DATA_LOG_FILE, mode='r') as file:
        reader = csv.reader(file)
        for row in reader:
            timestamps.append(row[0])
            gpu_1_temps.append(int(row[1]))
            gpu_2_temps.append(int(row[2]))
            fan_1_speeds.append(float(row[3]))
            fan_2_speeds.append(float(row[4]))

    # Limit the data to the latest N points
    timestamps = timestamps[-NUM_POINTS_TO_PLOT:]
    gpu_1_temps = gpu_1_temps[-NUM_POINTS_TO_PLOT:]
    gpu_2_temps = gpu_2_temps[-NUM_POINTS_TO_PLOT:]
    fan_1_speeds = fan_1_speeds[-NUM_POINTS_TO_PLOT:]
    fan_2_speeds = fan_2_speeds[-NUM_POINTS_TO_PLOT:]

    # Create a figure with two subplots side by side
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 5), sharey=False)

    def plot_gpu(ax_temp, ax_fan, gpu_temps, fan_speeds, title):
        ax_temp.plot(timestamps, gpu_temps, marker='o', color='green', label=f'{title} Temperature (°C)')
        ax_fan.plot(timestamps, fan_speeds, marker='x', color='red', label=f'Fan Speed')
        ax_temp.axhline(y=TEMPERATURE_TARGET, color='g', linestyle='--', label=f'Target Temperature ({TEMPERATURE_TARGET}°C)')
        ax_temp.set_title(title)
        ax_temp.set_xlabel('Timestamp')
        ax_temp.set_ylabel('Temperature (°C)', color='green')
        ax_fan.set_ylabel('Fan Speed (%)', color='red')
        ax_temp.tick_params(axis='y', labelcolor='green')
        ax_fan.tick_params(axis='y', labelcolor='orange')
        ax_temp.legend(loc='upper left')
        ax_fan.legend(loc='upper right')
        ax_temp.grid(True)
        ax_temp.set_ylim(0, 100)  # Set y-axis limits to between 0 and 100
        ax_fan.set_ylim(FAN_SPEED_MIN, 100)  # Set y-axis limits for fan speed

    plot_gpu(ax1, ax1.twinx(), gpu_1_temps, fan_1_speeds, "GPU 1")
    plot_gpu(ax2, ax2.twinx(), gpu_2_temps, fan_2_speeds, "GPU 2")
    # Save the plot as a JPEG file
    plot_file = "gpu_temperatures_side_by_side.jpg"
    plt.savefig(plot_file)
    plt.close()
    return plot_file

@app.route('/')
def index():
    """Displays the plot and nvidia-smi output on the web page with modern styling."""
    nvidia_output = fetch_nvidia_smi_output()
    ollama_output = fetch_ollama_ps_output()
    gpu_temps = get_gpu_temperatures()
    return render_template("index.html",
                           nvidia_output=nvidia_output,
                           ollama_output=ollama_output,
                           gpu_temps=gpu_temps,
                           fan_speeds=current_fan_speeds,
                           adjusted_fan_speeds=adjusted_fan_speeds)
@app.route('/stop_ollama_model')
def stop_ollama_model():
    """Stops a specified Ollama model."""
    model_name = request.args.get('model_name')
    if model_name:
        subprocess.run(["ollama", "stop", model_name])
    return redirect('/')

@app.route('/fan_control')
def fan_control():
    """Controls the fan speed using a PID controller."""
    #try:
    nvidia_output = subprocess.check_output(['nvidia-smi', '-q'])
    lines = nvidia_output.decode().split('\n')
    gpu_temps = [float(line.split(':')[1].strip()[:-2]) for line in lines if 'GPU Current Temp' in line]

    fan_speed_deltas = [pid(temp) for pid, temp in zip(fan_pid_controllers, gpu_temps)]
    for i, (temp, delta) in enumerate(zip(gpu_temps, fan_speed_deltas)):
        # Only update the fan speed if the temperature is above target or already adjusted
        if temp >= TEMPERATURE_TARGET or current_fan_speeds[i] > 0:
            current_fan_speeds[i] -= 0.1 * delta
            current_fan_speeds[i] = max(FAN_SPEED_MIN, min(current_fan_speeds[i], 100))
            adjusted_fan_speeds[i] = 0 if current_fan_speeds[i] < FAN_SPEED_MIN + 1e-3 else current_fan_speeds[i]

    return jsonify({
            'gpu_temps': gpu_temps,
            'fan_speed': adjusted_fan_speeds,
            'fan_speed_deltas': fan_speed_deltas,
    })
    #except Exception as e:
    #    print(f"Error in fan control: {e}")
    #    return jsonify({'error': str(e)}), 500

@app.route('/plot')
def plot():
    """Serves the temperature plot as an image."""
    plot_file = generate_temperature_plot()
    if plot_file:
        return send_file(plot_file, mimetype='image/jpeg')
    return "No temperature data available."

def log_data_periodically():
    """Logs GPU temperatures and fan speeds periodically."""
    while True:
        try:
            temps = get_gpu_temperatures()
            with open(DATA_LOG_FILE, mode='a', newline='') as file:
                writer = csv.writer(file)
                writer.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), temps[0], temps[1],
                                adjusted_fan_speeds[0], adjusted_fan_speeds[1]])
            print(f"Logged temperature: {temps}°C")
            print(f"Logged fan speed: {adjusted_fan_speeds}%")
        except Exception as e:
            print(f"Error logging data: {e}")
        time.sleep(60)  # Log every minute

if __name__ == "__main__":
    # Start a separate thread to log the temperature and USB state every minute
    threading.Thread(target=log_data_periodically, daemon=True).start()
    
    # Run the Flask app
    app.run(host='0.0.0.0', port=5000)
