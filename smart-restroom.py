import tkinter as tk
from tkinter import ttk, font
import threading
import random
import time
from datetime import datetime
from threading import Lock
import psutil

class ModuleBase:
    def __init__(self):
        self.running = False
        self.paused = False
        self.thread = None
        self.lock = threading.Lock()
        
    def start(self):
        if not self.running:
            self.running = True
            self.paused = False
            self.thread = threading.Thread(target=self.run)
            self.thread.daemon = True
            self.thread.start()
            
    def pause(self):
        self.paused = not self.paused
        
    def restart(self):
        self.running = False
        if self.thread:
            self.thread.join()
        self.start()
        
    def run(self):
        pass

class OccupancyModule(ModuleBase):
    def __init__(self):
        super().__init__()
        self.occupied = False
        self.visitor_count = 0
        self.current_duration = 0
        self.total_duration = 0
        self.sensor_online = True
        
    def run(self):
        while self.running:
            if not self.paused:
                with self.lock:
                    # Simulate occupancy changes
                    if random.random() < 0.1:
                        self.occupied = not self.occupied
                        if self.occupied:
                            self.visitor_count += 1
                        self.current_duration = random.randint(30, 180)
                        self.total_duration += self.current_duration
            time.sleep(1)

class OdorModule(ModuleBase):
    def __init__(self):
        super().__init__()
        self.sensors = {
            f"sensor_{i}": {
                "gas": {"online": True, "aqi": 0},
                "temp": {"online": True, "temp": 0, "humidity": 0}
            } for i in range(1, 5)
        }
        
    def run(self):
        while self.running:
            if not self.paused:
                with self.lock:
                    for sensor in self.sensors.values():
                        sensor["gas"]["aqi"] = random.randint(0, 500)
                        sensor["temp"]["temp"] = random.uniform(20, 30)
                        sensor["temp"]["humidity"] = random.uniform(30, 70)
            time.sleep(1)

class DispenserModule(ModuleBase):
    def __init__(self):
        super().__init__()
        self.containers = {
            f"container_{i}": {
                "volume": 425,
                "type": f"Liquid {i}",
                "online": True,
                "last_dispense": 0,
                "last_time": datetime.now().strftime("%H:%M:%S")
            } for i in range(1, 5)
        }
        
    def run(self):
        while self.running:
            if not self.paused:
                with self.lock:
                    for container in self.containers.values():
                        if random.random() < 0.1:
                            dispense = random.randint(5, 20)
                            container["volume"] = max(0, container["volume"] - dispense)
                            container["last_dispense"] = dispense
                            container["last_time"] = datetime.now().strftime("%H:%M:%S")
            time.sleep(1)

class CentralHub:
    def __init__(self):
        self.lock = threading.Lock()
        self.raspberry_pi = {
            "status": "UP",
            "last_powered": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "cpu_temp": 45.0,
            "cpu_usage": 25.0,
            "memory_usage": 40.0,
            "storage_usage": 35.0
        }
        self.arduino_uno = {
            "status": "UP",
            "last_powered": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "cpu_temp": 35.0,
            "cpu_usage": 15.0,
            "memory_usage": 30.0,
            "flash_usage": 25.0
        }
        
    def update_stats(self):
        with self.lock:
            # Simulate Raspberry Pi stats
            self.raspberry_pi["cpu_temp"] = random.uniform(40, 55)
            self.raspberry_pi["cpu_usage"] = psutil.cpu_percent()
            self.raspberry_pi["memory_usage"] = psutil.virtual_memory().percent
            self.raspberry_pi["storage_usage"] = psutil.disk_usage('/').percent
            
            # Simulate Arduino stats
            self.arduino_uno["cpu_temp"] = random.uniform(30, 45)
            self.arduino_uno["cpu_usage"] = random.uniform(10, 30)
            self.arduino_uno["memory_usage"] = random.uniform(20, 40)
            self.arduino_uno["flash_usage"] = random.uniform(20, 35)

class SmartRestroomGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Smart Restroom System: Developer Contol Panel")
        self.root.geometry("1200x800")
        self.root.resizable(False, False)  # Disable window resizing
        
        # Define heading styles
        self.h1_font = font.Font(family="Arial", size=24, weight="bold")
        self.h2_font = font.Font(family="Arial", size=20, weight="bold")
        self.h3_font = font.Font(family="Arial", size=16, weight="bold")
        self.h4_font = font.Font(family="Arial", size=14, weight="bold")
        
        # Configure styles
        style = ttk.Style()
        style.configure('TLabelframe', borderwidth=2, relief="solid")
        style.configure('TLabelframe.Label', font=self.h3_font)
        style.configure('Rounded.TButton', borderwidth=0, relief="flat")
        
        # Initialize modules and central hub
        self.central_hub = CentralHub()
        self.occupancy_module = OccupancyModule()
        self.odor_module = OdorModule()
        self.dispenser_module = DispenserModule()
        
        self.setup_gui()
        self.update_gui()
        
    def setup_gui(self):
        # Create main container with two frames
        main_container = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_container.pack(fill=tk.BOTH, expand=True)
        
        # Left canvas (control panel)
        left_frame = ttk.Frame(main_container, width=300)
        main_container.add(left_frame)
        self.setup_left_panel(left_frame)
        
        # Right canvas (module displays)
        right_frame = ttk.Frame(main_container)
        main_container.add(right_frame)
        self.setup_right_panel(right_frame)

    def setup_left_panel(self, frame):
        # Section 1: Main Control
        section1 = ttk.Frame(frame)
        section1.pack(fill=tk.X, padx=10, pady=10)
        
        # Header with H1 style
        header = ttk.Label(section1, text="Smart Restroom", font=self.h1_font)
        header.pack(pady=20)
        
        # Description
        desc = ttk.Label(section1, text="An intelligent system for\nrestroom management.", 
                        wraplength=250, justify=tk.LEFT)
        desc.pack(pady=10)
        
        # Main START button with rounded corners
        self.main_start_button = tk.Button(section1, text="START", 
                                         command=self.toggle_all_modules,
                                         bg="green", fg="white", 
                                         font=("Arial", 18, "bold"),
                                         width=10, height=5,
                                         relief="groove",
                                         borderwidth=0)
        self.main_start_button.pack(pady=30)
        
        # Separator
        ttk.Separator(frame, orient='horizontal').pack(fill=tk.X, padx=10, pady=10)
        
        # Section 2: Central Hub
        section2 = ttk.Frame(frame)
        section2.pack(fill=tk.X, padx=10, pady=10)
        
        hub_header = ttk.Label(section2, text="Central Hub", font=self.h2_font)
        hub_header.pack(pady=10)
        
        hub_desc = ttk.Label(section2, 
                           text="Check system status and condition of the Central Hub",
                           wraplength=250)
        hub_desc.pack(pady=5)
        
        # Create frames for Raspberry Pi and Arduino Uno
        controllers_frame = ttk.Frame(section2)
        controllers_frame.pack(fill=tk.X, pady=10)
        
        # Raspberry Pi Frame
        rpi_frame = ttk.LabelFrame(controllers_frame, text="Raspberry Pi")
        rpi_frame.pack(side=tk.LEFT, padx=5, expand=True, fill=tk.BOTH)
        
        self.rpi_status = ttk.Label(rpi_frame, text="Status: UP")
        self.rpi_status.pack(anchor=tk.W, padx=5, pady=2)
        
        self.rpi_last_powered = ttk.Label(rpi_frame, 
                                        text="Last Powered: 2025-04-28 01:11:00")
        self.rpi_last_powered.pack(anchor=tk.W, padx=5, pady=2)
        
        self.rpi_cpu_temp = ttk.Label(rpi_frame, text="CPU Temp: 45.0°C")
        self.rpi_cpu_temp.pack(anchor=tk.W, padx=5, pady=2)
        
        self.rpi_cpu_usage = ttk.Label(rpi_frame, text="CPU Usage: 25.0%")
        self.rpi_cpu_usage.pack(anchor=tk.W, padx=5, pady=2)
        
        self.rpi_memory_usage = ttk.Label(rpi_frame, text="Memory Usage: 40.0%")
        self.rpi_memory_usage.pack(anchor=tk.W, padx=5, pady=2)
        
        self.rpi_storage_usage = ttk.Label(rpi_frame, text="Storage Usage: 35.0%")
        self.rpi_storage_usage.pack(anchor=tk.W, padx=5, pady=2)
        
        # Arduino Uno Frame
        arduino_frame = ttk.LabelFrame(controllers_frame, text="Arduino Uno")
        arduino_frame.pack(side=tk.LEFT, padx=5, expand=True, fill=tk.BOTH)
        
        self.arduino_status = ttk.Label(arduino_frame, text="Status: UP")
        self.arduino_status.pack(anchor=tk.W, padx=5, pady=2)
        
        self.arduino_last_powered = ttk.Label(arduino_frame, 
                                            text="Last Powered: 2025-04-28 01:11:00")
        self.arduino_last_powered.pack(anchor=tk.W, padx=5, pady=2)
        
        self.arduino_cpu_temp = ttk.Label(arduino_frame, text="CPU Temp: 35.0°C")
        self.arduino_cpu_temp.pack(anchor=tk.W, padx=5, pady=2)
        
        self.arduino_cpu_usage = ttk.Label(arduino_frame, text="CPU Usage: 15.0%")
        self.arduino_cpu_usage.pack(anchor=tk.W, padx=5, pady=2)
        
        self.arduino_memory_usage = ttk.Label(arduino_frame, text="Memory Usage: 30.0%")
        self.arduino_memory_usage.pack(anchor=tk.W, padx=5, pady=2)
        
        self.arduino_flash_usage = ttk.Label(arduino_frame, text="Flash Usage: 25.0%")
        self.arduino_flash_usage.pack(anchor=tk.W, padx=5, pady=2)

    def setup_right_panel(self, frame):
        # Create frames for each module
        self.setup_occupancy_section(ttk.LabelFrame(frame, text="Occupancy Module"))
        self.setup_odor_section(ttk.LabelFrame(frame, text="Odor Module"))
        self.setup_dispenser_section(ttk.LabelFrame(frame, text="Dispenser Module"))

    def setup_occupancy_section(self, frame):
        frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Control buttons row
        controls = ttk.Frame(frame)
        controls.pack(fill=tk.X, padx=5, pady=5)
        
        # Create horizontal container
        content_frame = ttk.Frame(frame)
        content_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Left side: Status display
        left_frame = ttk.Frame(content_frame)
        left_frame.pack(side=tk.LEFT, padx=10)
        
        self.occupancy_status = tk.Label(left_frame, text="VACANT", 
                                       width=15, height=5, 
                                       relief=tk.GROOVE,
                                       borderwidth=0)
        self.occupancy_status.pack(pady=5)
        
        # Right side: Description and stats
        right_frame = ttk.Frame(content_frame)
        right_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)
        
        ttk.Label(right_frame, 
                 text="Tracks visitor entries and exits in the restroom cubicle.",
                 wraplength=400, justify=tk.LEFT).pack(anchor=tk.W)
        
        # Sensor status
        self.occupancy_sensor_status = ttk.Label(right_frame, text="Sensor: UP")
        self.occupancy_sensor_status.pack(pady=5)
        
        # Statistics
        stats_frame = ttk.Frame(right_frame)
        stats_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.visitor_count_label = ttk.Label(stats_frame, text="Total Visitors: 0")
        self.visitor_count_label.pack()
        
        self.duration_label = ttk.Label(stats_frame, text="Recent Duration: 0s")
        self.duration_label.pack()
        
        self.avg_duration_label = ttk.Label(stats_frame, text="Avg Duration: 0s")
        self.avg_duration_label.pack()

    def setup_odor_section(self, frame):
        frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Control buttons
        controls = ttk.Frame(frame)
        controls.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(controls, text="START", 
                  command=self.odor_module.start).pack(side=tk.LEFT, padx=2)
        ttk.Button(controls, text="PAUSE", 
                  command=self.odor_module.pause).pack(side=tk.LEFT, padx=2)
        ttk.Button(controls, text="RESTART", 
                  command=self.odor_module.restart).pack(side=tk.LEFT, padx=2)
        
        # Description with left justification
        ttk.Label(frame, 
                 text="Monitors air quality and climate for a fresh environment.",
                 wraplength=400, justify=tk.LEFT).pack(anchor=tk.W, padx=5, pady=5)
        
        # Sensor display
        sensors_frame = ttk.Frame(frame)
        sensors_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.sensor_displays = {}
        for i in range(1, 5):
            sensor_frame = ttk.LabelFrame(sensors_frame, text=f"Sensor {i}")
            sensor_frame.pack(side=tk.LEFT, padx=5, expand=True)
            
            self.sensor_displays[f"sensor_{i}"] = {
                "gas": ttk.Label(sensor_frame, text="GAS: UP\nAQI: 0"),
                "temp": ttk.Label(sensor_frame, 
                                text="TEMP: UP\nTemp: 0°C\nHumidity: 0%")
            }
            
            self.sensor_displays[f"sensor_{i}"]["gas"].pack(pady=2)
            self.sensor_displays[f"sensor_{i}"]["temp"].pack(pady=2)

    def setup_dispenser_section(self, frame):
        frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Control buttons
        controls = ttk.Frame(frame)
        controls.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(controls, text="START", 
                  command=self.dispenser_module.start).pack(side=tk.LEFT, padx=2)
        ttk.Button(controls, text="PAUSE", 
                  command=self.dispenser_module.pause).pack(side=tk.LEFT, padx=2)
        ttk.Button(controls, text="RESTART", 
                  command=self.dispenser_module.restart).pack(side=tk.LEFT, padx=2)
        
        # Description with left justification
        ttk.Label(frame, 
                 text="Monitors liquid levels in four containers.",
                 wraplength=400, justify=tk.LEFT).pack(anchor=tk.W, padx=5, pady=5)
        
        # Container display
        containers_frame = ttk.Frame(frame)
        containers_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.container_displays = {}
        for i in range(1, 5):
            container_frame = ttk.LabelFrame(containers_frame, text=f"Container {i}")
            container_frame.pack(side=tk.LEFT, padx=5, expand=True)
            
            self.container_displays[f"container_{i}"] = {
                "percentage": ttk.Label(container_frame, text="100%"),
                "canvas": tk.Canvas(container_frame, width=50, height=100),
                "info": ttk.Label(container_frame, 
                                text="Status: UP\nVolume: 425mL\n" +
                                     f"Type: Liquid {i}\nLast Used: 0mL\n" +
                                     "Recent: 00:00:00")
            }
            
            self.container_displays[f"container_{i}"]["percentage"].pack(pady=2)
            self.container_displays[f"container_{i}"]["canvas"].pack(pady=2)
            self.container_displays[f"container_{i}"]["info"].pack(pady=2)

    def toggle_all_modules(self):
        if self.occupancy_module.running:
            self.main_start_button.config(text="START", bg="green")
            self.occupancy_module.running = False
            self.odor_module.running = False
            self.dispenser_module.running = False
        else:
            self.main_start_button.config(text="STOP", bg="red")
            self.occupancy_module.start()
            self.odor_module.start()
            self.dispenser_module.start()

    def update_gui(self):
        # Update Central Hub information
        self.central_hub.update_stats()
        with self.central_hub.lock:
            # Update Raspberry Pi stats
            rpi = self.central_hub.raspberry_pi
            self.rpi_status.config(text=f"Status: {rpi['status']}")
            self.rpi_last_powered.config(text=f"Last Powered: {rpi['last_powered']}")
            self.rpi_cpu_temp.config(text=f"CPU Temp: {rpi['cpu_temp']:.1f}°C")
            self.rpi_cpu_usage.config(text=f"CPU Usage: {rpi['cpu_usage']:.1f}%")
            self.rpi_memory_usage.config(text=f"Memory Usage: {rpi['memory_usage']:.1f}%")
            self.rpi_storage_usage.config(text=f"Storage Usage: {rpi['storage_usage']:.1f}%")
            
            # Update Arduino stats
            arduino = self.central_hub.arduino_uno
            self.arduino_status.config(text=f"Status: {arduino['status']}")
            self.arduino_last_powered.config(
                text=f"Last Powered: {arduino['last_powered']}")
            self.arduino_cpu_temp.config(text=f"CPU Temp: {arduino['cpu_temp']:.1f}°C")
            self.arduino_cpu_usage.config(text=f"CPU Usage: {arduino['cpu_usage']:.1f}%")
            self.arduino_memory_usage.config(
                text=f"Memory Usage: {arduino['memory_usage']:.1f}%")
            self.arduino_flash_usage.config(
                text=f"Flash Usage: {arduino['flash_usage']:.1f}%")

        # Update Module displays
        with self.occupancy_module.lock:
            status = "OCCUPIED" if self.occupancy_module.occupied else "VACANT"
            sensor_status = "UP" if self.occupancy_module.sensor_online else "DOWN"
            color = "red" if self.occupancy_module.occupied else "green"
            self.occupancy_status.config(text=status, bg=color)
            self.occupancy_sensor_status.config(text=f"Sensor: {sensor_status}")
            
            self.visitor_count_label.config(
                text=f"Total Visitors: {self.occupancy_module.visitor_count}")
            self.duration_label.config(
                text=f"Recent Duration: {self.occupancy_module.current_duration}s")
            
            avg_duration = (self.occupancy_module.total_duration / 
                          max(1, self.occupancy_module.visitor_count))
            self.avg_duration_label.config(text=f"Avg Duration: {int(avg_duration)}s")

        # Update Odor Module display
        with self.odor_module.lock:
            for sensor_id, sensor_data in self.odor_module.sensors.items():
                gas_display = self.sensor_displays[sensor_id]["gas"]
                temp_display = self.sensor_displays[sensor_id]["temp"]
                
                gas_display.config(
                    text=f"GAS: {'UP' if sensor_data['gas']['online'] else 'DOWN'}\n" +
                         f"AQI: {sensor_data['gas']['aqi']}")
                
                temp_display.config(
                    text=f"TEMP: {'UP' if sensor_data['temp']['online'] else 'DOWN'}\n" +
                         f"Temp: {sensor_data['temp']['temp']:.1f}°C\n" +
                         f"Humidity: {sensor_data['temp']['humidity']:.1f}%")

        # Update Dispenser Module display with percentage
        with self.dispenser_module.lock:
            for container_id, container_data in self.dispenser_module.containers.items():
                canvas = self.container_displays[container_id]["canvas"]
                info = self.container_displays[container_id]["info"]
                percentage = self.container_displays[container_id]["percentage"]
                
                # Update percentage
                percent = int((container_data["volume"] / 425) * 100)
                percentage.config(text=f"{percent}%")
                
                # Get color based on percentage
                color = self.get_volume_color(percent)
                
                # Clear and redraw volume bar with rounded corners and dynamic color
                canvas.delete("all")
                height = (container_data["volume"] / 425) * 90
                self.rounded_rectangle(canvas, 10, 100-height, 40, 100, radius=5, fill=color, outline="")
                
                info.config(
                    text=f"Status: {'UP' if container_data['online'] else 'DOWN'}\n" +
                         f"Volume: {container_data['volume']}mL\n" +
                         f"Type: {container_data['type']}\n" +
                         f"Last Used: {container_data['last_dispense']}mL\n" +
                         f"Recent: {container_data['last_time']}")

        # Schedule next update
        self.root.after(500, self.update_gui)

    # Add a color gradient function to determine the volume level color
    def get_volume_color(self, percentage):
        """
        Returns a color based on percentage:
        - Full (70-100%): Green
        - Medium (30-69%): Transitions from yellow to orange
        - Low (0-29%): Red
        """
        if percentage >= 70:
            # Green for high levels
            return "#4CAF50"
        elif percentage >= 30:
            # Calculate a gradient from yellow to orange
            # As percentage decreases from 70 to 30, we transition from yellow to orange
            yellow = (255, 235, 59)  # RGB for yellow
            orange = (255, 152, 0)   # RGB for orange
            
            # Calculate ratio (0 = 30%, 1 = 70%)
            ratio = (percentage - 30) / 40
            
            # Interpolate between yellow and orange
            r = int(yellow[0] * ratio + orange[0] * (1 - ratio))
            g = int(yellow[1] * ratio + orange[1] * (1 - ratio))
            b = int(yellow[2] * ratio + orange[2] * (1 - ratio))
            
            return f"#{r:02x}{g:02x}{b:02x}"
        else:
            # Red for low levels
            return "#F44336"

    # Add a helper function for rounded rectangles
    def rounded_rectangle(self, canvas, x1, y1, x2, y2, radius=10, **kwargs):
        """Draw a rounded rectangle on a canvas"""
        points = [
            x1 + radius, y1,
            x2 - radius, y1,
            x2, y1,
            x2, y1 + radius,
            x2, y2 - radius,
            x2, y2,
            x2 - radius, y2,
            x1 + radius, y2,
            x1, y2,
            x1, y2 - radius,
            x1, y1 + radius,
            x1, y1
        ]
        
        return canvas.create_polygon(points, **kwargs, smooth=True)

if __name__ == "__main__":
    root = tk.Tk()
    app = SmartRestroomGUI(root)
    root.mainloop()