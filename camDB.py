from PySide2 import QtWidgets, QtCore
import hou
import urllib.request
import urllib.error
import json
import gzip
import os
import platform
from pathlib import Path
import hashlib
import datetime


DEBUG_MODE = False  # <-- TOGGLE DEBUGGING HERE
API_BASE_URL = "https://camdb.matchmovemachine.com"

def debug_log(*args, **kwargs):
    """Prints messages only if DEBUG_MODE is True."""
    if DEBUG_MODE:
        print("DEBUG:", *args, **kwargs)

# Keep a module-level reference so Python doesn't garbage-collect the window
camdb_win = None

class CamDBPanel(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super(CamDBPanel, self).__init__(parent)
        self.setWindowTitle("CamDB Houdini Camera Browser")
        self.resize(900, 700)
        
        # Initialize data storage
        self._init_data_storage()
        
        # Initialize cache system
        self._init_cache_system()
        
        # Setup the user interface
        self._setup_ui()
        
        # Connect all signals
        self._connect_signals()
        
        # Load cached data if available
        self._load_cached_data()
    
    def _init_data_storage(self):
        """Initialize data storage variables"""
        self.camera_data = []
        self.filtered_cameras = []
        self.selected_camera = None
        self.sensor_data = []
    
    def _init_cache_system(self):
        """Initialize cache system with default paths"""
        self.cache_dir = self._get_default_cache_dir()
        self.cameras_cache_file = self.cache_dir / "camdb_cameras.json"
        self.cache_info_file = self.cache_dir / "camdb_cache_info.json"
        
        # Ensure cache directory exists
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_default_cache_dir(self):
        """Get the default cache directory based on OS"""
        system = platform.system()
        
        if system == "Windows":
            # Use APPDATA or USERPROFILE
            if "APPDATA" in os.environ:
                base_dir = Path(os.environ["APPDATA"])
            else:
                base_dir = Path.home()
            cache_dir = base_dir / "CamDB"
        elif system == "Darwin":  # macOS
            cache_dir = Path.home() / "Library" / "Application Support" / "CamDB"
        else:  # Linux and other Unix-like systems
            # Use XDG_DATA_HOME or default to ~/.local/share
            if "XDG_DATA_HOME" in os.environ:
                base_dir = Path(os.environ["XDG_DATA_HOME"])
            else:
                base_dir = Path.home() / ".local" / "share"
            cache_dir = base_dir / "CamDB"
        
        return cache_dir
    
    def _setup_ui(self):
        """Setup the complete user interface"""
        main_layout = QtWidgets.QVBoxLayout(self)
        
        # Setup each section of the UI
        self._setup_header_section(main_layout)
        self._setup_cache_section(main_layout)
        self._setup_filter_section(main_layout)
        self._setup_main_content(main_layout)
    
    def _setup_header_section(self, main_layout):
        """Setup the header section with load button and status"""
        load_layout = QtWidgets.QHBoxLayout()
        
        self.load_all_button = QtWidgets.QPushButton("Load All Cameras from CamDB")
        self.load_all_button.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; font-weight: bold; padding: 8px; }")
        load_layout.addWidget(self.load_all_button)
        
        self.status_label = QtWidgets.QLabel("Click 'Load All Cameras' to start or use cached data")
        load_layout.addWidget(self.status_label)
        load_layout.addStretch()
        
        main_layout.addLayout(load_layout)
    
    def _setup_cache_section(self, main_layout):
        """Setup the cache management section"""
        cache_frame = QtWidgets.QGroupBox("Cache Management")
        cache_layout = QtWidgets.QVBoxLayout(cache_frame)
        
        # Cache info and controls row
        cache_info_layout = QtWidgets.QHBoxLayout()
        
        self.cache_info_label = QtWidgets.QLabel("No cache data available")
        cache_info_layout.addWidget(self.cache_info_label)
        
        cache_info_layout.addStretch()
        
        self.use_cache_button = QtWidgets.QPushButton("Use Cached Data")
        self.use_cache_button.setEnabled(False)
        cache_info_layout.addWidget(self.use_cache_button)
        
        self.update_cache_button = QtWidgets.QPushButton("Update Cache")
        cache_info_layout.addWidget(self.update_cache_button)
        
        self.clear_cache_button = QtWidgets.QPushButton("Clear Cache")
        cache_info_layout.addWidget(self.clear_cache_button)
        
        cache_layout.addLayout(cache_info_layout)
        
        # Cache location row
        location_layout = QtWidgets.QHBoxLayout()
        
        location_layout.addWidget(QtWidgets.QLabel("Cache Location:"))
        self.cache_location_edit = QtWidgets.QLineEdit(str(self.cache_dir))
        self.cache_location_edit.setReadOnly(True)
        location_layout.addWidget(self.cache_location_edit)
        
        self.browse_cache_button = QtWidgets.QPushButton("Browse...")
        location_layout.addWidget(self.browse_cache_button)
        
        cache_layout.addLayout(location_layout)
        
        main_layout.addWidget(cache_frame)
    
    def _setup_filter_section(self, main_layout):
        """Setup the filter controls section"""
        filter_layout = QtWidgets.QHBoxLayout()
        
        # Camera make dropdown
        make_layout = QtWidgets.QVBoxLayout()
        make_layout.addWidget(QtWidgets.QLabel("Filter by Make:"))
        self.make_combo = QtWidgets.QComboBox()
        self.make_combo.addItem("All Makes")
        make_layout.addWidget(self.make_combo)
        filter_layout.addLayout(make_layout)
        
        # Camera type dropdown
        type_layout = QtWidgets.QVBoxLayout()
        type_layout.addWidget(QtWidgets.QLabel("Filter by Type:"))
        self.type_combo = QtWidgets.QComboBox()
        self.type_combo.addItem("All Types")
        type_layout.addWidget(self.type_combo)
        filter_layout.addLayout(type_layout)
        
        # Search box
        search_layout = QtWidgets.QVBoxLayout()
        search_layout.addWidget(QtWidgets.QLabel("Search Name:"))
        self.search_edit = QtWidgets.QLineEdit()
        self.search_edit.setPlaceholderText("Search camera names...")
        search_layout.addWidget(self.search_edit)
        filter_layout.addLayout(search_layout)
        
        filter_layout.addStretch()
        main_layout.addLayout(filter_layout)
    
    def _setup_main_content(self, main_layout):
        """Setup the main content area with splitter and panels"""
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        main_layout.addWidget(splitter)
        
        # Setup left and right panels
        self._setup_camera_list_panel(splitter)
        self._setup_details_panel(splitter)
        
        splitter.setSizes([300, 500])
    
    def _setup_camera_list_panel(self, splitter):
        """Setup the left panel with camera list"""
        left_widget = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_widget)
        left_layout.addWidget(QtWidgets.QLabel("Cameras:"))
        
        self.camera_list = QtWidgets.QListWidget()
        self.camera_list.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        left_layout.addWidget(self.camera_list)
        
        splitter.addWidget(left_widget)
    
    def _setup_details_panel(self, splitter):
        """Setup the right panel with camera details and controls"""
        right_widget = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right_widget)
        
        # Camera info section
        right_layout.addWidget(QtWidgets.QLabel("Camera Details:"))
        self.camera_info = QtWidgets.QTextEdit()
        self.camera_info.setMaximumHeight(100)
        self.camera_info.setReadOnly(True)
        right_layout.addWidget(self.camera_info)
        
        # Load sensors button
        self.load_sensors_button = QtWidgets.QPushButton("Load Sensor Data for Selected Camera")
        self.load_sensors_button.setEnabled(False)
        right_layout.addWidget(self.load_sensors_button)
        
        # Sensor data section
        right_layout.addWidget(QtWidgets.QLabel("Available Sensor Configurations:"))
        self.sensor_list = QtWidgets.QListWidget()
        right_layout.addWidget(self.sensor_list)
        
        # Sensor details
        right_layout.addWidget(QtWidgets.QLabel("Sensor Details:"))
        self.sensor_info = QtWidgets.QTextEdit()
        self.sensor_info.setMaximumHeight(150)
        self.sensor_info.setReadOnly(True)
        right_layout.addWidget(self.sensor_info)
        
        # Create camera button
        self.create_camera_button = QtWidgets.QPushButton("Create Camera in Houdini")
        self.create_camera_button.setStyleSheet("QPushButton { background-color: #2196F3; color: white; font-weight: bold; padding: 10px; }")
        self.create_camera_button.setEnabled(False)
        right_layout.addWidget(self.create_camera_button)
        
        splitter.addWidget(right_widget)
    
    def _connect_signals(self):
        """Connect all UI signals to their respective handlers"""
        self.load_all_button.clicked.connect(self.load_all_cameras)
        self.make_combo.currentTextChanged.connect(self.filter_cameras)
        self.type_combo.currentTextChanged.connect(self.filter_cameras)
        self.search_edit.textChanged.connect(self.filter_cameras)
        self.camera_list.currentItemChanged.connect(self.on_camera_selected)
        self.load_sensors_button.clicked.connect(self.load_sensor_data)
        self.sensor_list.currentItemChanged.connect(self.on_sensor_selected)
        self.create_camera_button.clicked.connect(self.create_houdini_camera)
        
        # Cache management signals
        self.use_cache_button.clicked.connect(self.use_cached_data)
        self.update_cache_button.clicked.connect(self.update_cache)
        self.clear_cache_button.clicked.connect(self.clear_cache)
        self.browse_cache_button.clicked.connect(self.browse_cache_location)
    
    def _get_api_version_hash(self, data):
        """Generate a hash of the API data to detect changes"""
        json_str = json.dumps(data, sort_keys=True)
        return hashlib.md5(json_str.encode()).hexdigest()
    
    def _save_cache_info(self, data_hash, timestamp):
        """Save cache metadata information"""
        cache_info = {
            "timestamp": timestamp,
            "data_hash": data_hash,
            "api_url": API_BASE_URL,
            "cache_version": "1.0"
        }
        
        try:
            with open(self.cache_info_file, 'w', encoding='utf-8') as f:
                json.dump(cache_info, f, indent=2)
        except Exception as e:
            debug_log(f"Error saving cache info: {e}")
    
    def _load_cache_info(self):
        """Load cache metadata information"""
        try:
            if self.cache_info_file.exists():
                with open(self.cache_info_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            debug_log(f"Error loading cache info: {e}")
        return None
    
    def _update_cache_info_display(self):
        """Update the cache info display in the UI"""
        cache_info = self._load_cache_info()
        
        if cache_info and self.cameras_cache_file.exists():
            timestamp = cache_info.get('timestamp', 'Unknown')
            try:
                # Parse timestamp and format it nicely
                dt = datetime.datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                formatted_time = dt.strftime('%Y-%m-%d %H:%M:%S')
                
                # Get file size
                file_size = self.cameras_cache_file.stat().st_size
                size_kb = file_size / 1024
                
                info_text = f"Cached: {formatted_time} ({size_kb:.1f} KB)"
                self.cache_info_label.setText(info_text)
                self.use_cache_button.setEnabled(True)
                
            except Exception as e:
                self.cache_info_label.setText(f"Cache available (error reading timestamp: {e})")
                self.use_cache_button.setEnabled(True)
        else:
            self.cache_info_label.setText("No cache data available")
            self.use_cache_button.setEnabled(False)
    
    def _load_cached_data(self):
        """Load cached data on startup if available"""
        self._update_cache_info_display()
        
        # If we have cached data, offer to use it
        if self.cameras_cache_file.exists():
            cache_info = self._load_cache_info()
            if cache_info:
                timestamp = cache_info.get('timestamp', 'Unknown time')
                self.status_label.setText(f"Cached data available from {timestamp}")
    
    def _save_to_cache(self, data):
        """Save camera data to cache with metadata"""
        try:
            # Save the camera data
            with open(self.cameras_cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            
            # Save cache metadata
            data_hash = self._get_api_version_hash(data)
            timestamp = datetime.datetime.now().isoformat()
            self._save_cache_info(data_hash, timestamp)
            
            debug_log(f"Data cached to {self.cameras_cache_file}")
            self._update_cache_info_display()
            
        except Exception as e:
            debug_log(f"Error saving to cache: {e}")
            self.status_label.setText(f"Error saving cache: {e}")
    
    def _load_from_cache(self):
        """Load camera data from cache"""
        try:
            if self.cameras_cache_file.exists():
                with open(self.cameras_cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            debug_log(f"Error loading from cache: {e}")
        return None
    
    def _check_cache_freshness(self):
        """Check if cached data is up to date with API"""
        try:
            # Get a small sample from API to check version
            sample_data = self.api_request("/cameras/?limit=1")
            current_hash = self._get_api_version_hash(sample_data)
            
            cache_info = self._load_cache_info()
            if cache_info:
                cached_hash = cache_info.get('data_hash', '')
                return current_hash == cached_hash
            
        except Exception as e:
            debug_log(f"Error checking cache freshness: {e}")
        
        return False
    
    def browse_cache_location(self):
        """Allow user to choose cache location"""
        current_dir = str(self.cache_dir)
        new_dir = QtWidgets.QFileDialog.getExistingDirectory(
            self, 
            "Choose Cache Directory", 
            current_dir
        )
        
        if new_dir:
            self.cache_dir = Path(new_dir) / "CamDB"
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            
            # Update file paths
            self.cameras_cache_file = self.cache_dir / "camdb_cameras.json"
            self.cache_info_file = self.cache_dir / "camdb_cache_info.json"
            
            # Update UI
            self.cache_location_edit.setText(str(self.cache_dir))
            self._update_cache_info_display()
            
            self.status_label.setText(f"Cache location changed to: {self.cache_dir}")
    
    def use_cached_data(self):
        """Load and use cached camera data"""
        cached_data = self._load_from_cache()
        
        if cached_data:
            self.camera_data = cached_data if isinstance(cached_data, list) else []
            self._populate_filters_and_display()
            
            cache_info = self._load_cache_info()
            timestamp = cache_info.get('timestamp', 'unknown time') if cache_info else 'unknown time'
            self.status_label.setText(f"Loaded {len(self.camera_data)} cameras from cache ({timestamp})")
        else:
            self.status_label.setText("Error loading cached data")
    
    def update_cache(self):
        """Update cache with latest data from API"""
        self.status_label.setText("Updating cache from API...")
        
        try:
            # Check if we have the latest version
            if self.cameras_cache_file.exists():
                self.status_label.setText("Checking for updates...")
                if self._check_cache_freshness():
                    self.status_label.setText("Cache is already up to date!")
                    return
            
            # Fetch fresh data
            data = self.api_request("/cameras/")
            camera_data = data if isinstance(data, list) else []
            
            # Save to cache
            self._save_to_cache(camera_data)
            
            # Load the data into the UI
            self.camera_data = camera_data
            self._populate_filters_and_display()
            
            self.status_label.setText(f"Cache updated with {len(self.camera_data)} cameras")
            
        except Exception as e:
            self.status_label.setText(f"Error updating cache: {e}")
    
    def clear_cache(self):
        """Clear cached data"""
        try:
            if self.cameras_cache_file.exists():
                self.cameras_cache_file.unlink()
            if self.cache_info_file.exists():
                self.cache_info_file.unlink()
            
            self.camera_data = []
            self.filtered_cameras = []
            self.camera_list.clear()
            self.make_combo.clear()
            self.type_combo.clear()
            self.make_combo.addItem("All Makes")
            self.type_combo.addItem("All Types")
            
            self._update_cache_info_display()
            self.status_label.setText("Cache cleared")
            
        except Exception as e:
            self.status_label.setText(f"Error clearing cache: {e}")

    def api_request(self, endpoint):
        """Make API request with proper headers"""
        url = f"{API_BASE_URL}{endpoint}"
        
        try:
            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
            req.add_header('Accept', 'application/json, text/plain, */*')
            req.add_header('Accept-Language', 'en-US,en;q=0.9')
            req.add_header('Connection', 'keep-alive')
            
            with urllib.request.urlopen(req) as response:
                raw_data = response.read()
                
                # Handle compression
                content_encoding = response.info().get('Content-Encoding', '').lower()
                if content_encoding == 'gzip':
                    raw_data = gzip.decompress(raw_data)
                elif content_encoding == 'deflate':
                    import zlib
                    raw_data = zlib.decompress(raw_data)
                
                encoding = response.info().get_content_charset("utf-8")
                text_data = raw_data.decode(encoding)
                return json.loads(text_data)
                
        except Exception as e:
            raise Exception(f"API request failed: {e}")

    def load_all_cameras(self):
        """Load all cameras from the API"""
        self.status_label.setText("Loading cameras from API...")
        self.load_all_button.setEnabled(False)
        
        try:
            # Load cameras from API
            data = self.api_request("/cameras/")
            self.camera_data = data if isinstance(data, list) else []
            
            # Save to cache
            self._save_to_cache(self.camera_data)
            
            # Populate UI
            self._populate_filters_and_display()
            
            self.status_label.setText(f"Loaded {len(self.camera_data)} cameras from API")
            
        except Exception as e:
            self.status_label.setText(f"Error loading cameras: {e}")
        
        finally:
            self.load_all_button.setEnabled(True)
    
    def _populate_filters_and_display(self):
        """Populate filter dropdowns and display cameras"""
        # Populate filter dropdowns
        makes = set()
        types = set()
        
        for camera in self.camera_data:
            if camera.get('make'):
                makes.add(camera['make'])
            if camera.get('cam_type'):
                types.add(camera['cam_type'])
        
        # Update make combo
        self.make_combo.clear()
        self.make_combo.addItem("All Makes")
        for make in sorted(makes):
            self.make_combo.addItem(make)
        
        # Update type combo
        self.type_combo.clear()
        self.type_combo.addItem("All Types")
        for cam_type in sorted(types):
            self.type_combo.addItem(cam_type)
        
        # Filter and display cameras
        self.filter_cameras()

    def filter_cameras(self):
        """Filter cameras based on selected criteria"""
        if not self.camera_data:
            return
        
        selected_make = self.make_combo.currentText()
        selected_type = self.type_combo.currentText()
        search_text = self.search_edit.text().lower()
        
        self.filtered_cameras = []
        
        for camera in self.camera_data:
            # Filter by make
            if selected_make != "All Makes" and camera.get('make') != selected_make:
                continue
            
            # Filter by type
            if selected_type != "All Types" and camera.get('cam_type') != selected_type:
                continue
            
            # Filter by search text
            if search_text and search_text not in camera.get('name', '').lower():
                continue
            
            self.filtered_cameras.append(camera)
        
        # Update camera list
        self.camera_list.clear()
        for camera in self.filtered_cameras:
            name = camera.get('name', 'Unknown')
            make = camera.get('make', 'Unknown')
            item_text = f"{make} - {name}"
            item = QtWidgets.QListWidgetItem(item_text)
            item.setData(QtCore.Qt.UserRole, camera)
            self.camera_list.addItem(item)

    def on_camera_selected(self, current, previous):
        """Handle camera selection"""
        if current:
            self.selected_camera = current.data(QtCore.Qt.UserRole)
            
            # Display camera info
            info = f"ID: {self.selected_camera.get('id', 'N/A')}\n"
            info += f"Make: {self.selected_camera.get('make', 'N/A')}\n"
            info += f"Name: {self.selected_camera.get('name', 'N/A')}\n"
            info += f"Type: {self.selected_camera.get('cam_type', 'N/A')}"
            
            self.camera_info.setPlainText(info)
            self.load_sensors_button.setEnabled(True)
            
            # Clear sensor data
            self.sensor_list.clear()
            self.sensor_info.clear()
            self.create_camera_button.setEnabled(False)
        else:
            self.selected_camera = None
            self.camera_info.clear()
            self.load_sensors_button.setEnabled(False)

    def load_sensor_data(self):
        """Load sensor data for the selected camera"""
        if not self.selected_camera:
            return
        
        camera_id = self.selected_camera.get('id')
        if not camera_id:
            return
        
        self.status_label.setText("Loading sensor data...")
        self.load_sensors_button.setEnabled(False)
        
        try:
            # Debug: Show what we're requesting
            endpoint = f"/cameras/{camera_id}/sensors/"
            debug_log(f"Requesting: {endpoint}")
            
            data = self.api_request(endpoint)
            
            # Debug: Show raw response
            debug_log(f"Raw sensor response: {data}")
            
            # Handle different response formats
            if isinstance(data, dict):
                # Check if it's wrapped in a 'sensors' key or similar
                if 'sensors' in data:
                    self.sensor_data = data['sensors']
                elif 'data' in data:
                    self.sensor_data = data['data']
                elif 'results' in data:
                    self.sensor_data = data['results']
                else:
                    # Might be a single sensor object, wrap in list
                    self.sensor_data = [data]
            elif isinstance(data, list):
                self.sensor_data = data
            else:
                self.sensor_data = []
            
            debug_log(f"Processed sensor data: {self.sensor_data}")
            
            # Populate sensor list
            self.sensor_list.clear()
            
            if not self.sensor_data:
                item = QtWidgets.QListWidgetItem("No sensor data available")
                self.sensor_list.addItem(item)
                self.status_label.setText("No sensor configurations found")
                return
            
            for i, sensor in enumerate(self.sensor_data):
                debug_log(f"Processing sensor {i}: {sensor}")
                
                mode = sensor.get('mode_name', f'Mode {i+1}')
                res_w = sensor.get('res_width', 'N/A')
                res_h = sensor.get('res_height', 'N/A')
                sensor_w = sensor.get('sensor_width', 'N/A')
                sensor_h = sensor.get('sensor_height', 'N/A')
                
                res = f"{res_w}x{res_h}"
                sensor_size = f"{sensor_w}x{sensor_h}mm"
                
                item_text = f"{mode} - {res} ({sensor_size})"
                item = QtWidgets.QListWidgetItem(item_text)
                item.setData(QtCore.Qt.UserRole, sensor)
                self.sensor_list.addItem(item)
            
            self.status_label.setText(f"Loaded {len(self.sensor_data)} sensor configurations")
            
        except urllib.error.HTTPError as http_err:
            error_msg = f"HTTP {http_err.code}: {http_err.reason}"
            try:
                error_body = http_err.read().decode('utf-8')
                error_msg += f"\nResponse: {error_body}"
            except:
                pass
            self.status_label.setText(f"HTTP Error: {error_msg}")
            debug_log(f"HTTP Error loading sensors: {error_msg}")
            
        except Exception as e:
            self.status_label.setText(f"Error loading sensors: {e}")
            print(f"Error loading sensors: {e}")
            import traceback
            traceback.print_exc()
        
        finally:
            self.load_sensors_button.setEnabled(True)

    def on_sensor_selected(self, current, previous):
        """Handle sensor selection"""
        if current:
            sensor = current.data(QtCore.Qt.UserRole)
            
            # Display sensor info
            info = f"Sensor ID: {sensor.get('id', 'N/A')}\n"
            info += f"Mode: {sensor.get('mode_name', 'N/A')}\n"
            info += f"Resolution: {sensor.get('res_width', 'N/A')} x {sensor.get('res_height', 'N/A')}\n"
            info += f"Sensor Size: {sensor.get('sensor_width', 'N/A')} x {sensor.get('sensor_height', 'N/A')} mm\n"
            info += f"Format Aspect: {sensor.get('format_aspect', 'N/A')}\n"
            info += f"Approved: {sensor.get('approve', 'N/A')}"
            
            self.sensor_info.setPlainText(info)
            self.create_camera_button.setEnabled(True)
        else:
            self.sensor_info.clear()
            self.create_camera_button.setEnabled(False)

    def create_houdini_camera(self):
        """Create a camera in Houdini with the selected settings"""
        if not self.selected_camera:
            hou.ui.displayMessage("No camera selected")
            return
        
        current_sensor_item = self.sensor_list.currentItem()
        if not current_sensor_item:
            hou.ui.displayMessage("No sensor configuration selected")
            return
        
        sensor = current_sensor_item.data(QtCore.Qt.UserRole)
        
        try:
            # Get current scene's object level
            obj = hou.node("/obj")
            
            # Create camera name
            camera_name = f"{self.selected_camera.get('make', 'Unknown')}_{self.selected_camera.get('name', 'Camera')}"
            camera_name = camera_name.replace(' ', '_').replace('-', '_')
            
            # Create the camera
            cam_node = obj.createNode("cam", camera_name)
            
            # Set camera parameters based on sensor data
            if sensor.get('res_width') and sensor.get('res_height'):
                cam_node.parm("resx").set(int(sensor['res_width']))
                cam_node.parm("resy").set(int(sensor['res_height']))
            
            if sensor.get('sensor_width'):
            
                # Convert sensor width
                aperture_houdini = (float(sensor['sensor_width']) / 36.0) * 41.4214
                cam_node.parm("aperture").set(aperture_houdini)
            
            # Set aspect ratio if available
            if sensor.get('format_aspect'):
                try:
                    aspect = float(sensor['format_aspect'])
                    cam_node.parm("aspect").set(aspect)
                except (ValueError, TypeError):
                    pass
            
            # Add camera info to the comment
            comment = f"CamDB Camera: {self.selected_camera.get('make')} {self.selected_camera.get('name')}\n"
            comment += f"Mode: {sensor.get('mode_name', 'N/A')}\n"
            comment += f"Sensor: {sensor.get('sensor_width')}x{sensor.get('sensor_height')}mm\n"
            comment += f"Resolution: {sensor.get('res_width')}x{sensor.get('res_height')}"
            
            cam_node.setComment(comment)
            cam_node.setGenericFlag(hou.nodeFlag.DisplayComment, True)
            
            # Position camera slightly away from origin
            cam_node.parmTuple("t").set((0, 0, 5))
            
            # Layout nodes
            cam_node.moveToGoodPosition()
            
            self.status_label.setText(f"Created camera: {camera_name}")
            
            # Ask if user wants to look through the camera
            if hou.ui.displayMessage("Camera created successfully! Look through it now?", 
                                   buttons=("Yes", "No")) == 0:
                # Set the camera as the current viewport camera
                scene_viewer = hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
                if scene_viewer:
                    scene_viewer.curViewport().setCamera(cam_node)
            
        except Exception as e:
            hou.ui.displayMessage(f"Error creating camera: {e}")
            self.status_label.setText(f"Error creating camera: {e}")

def show_camdb_floating():
    """
    Instantiate (or re-show) CamDBPanel as a floating window.
    Keeps a global camdb_win reference so it doesn't get garbage-collected.
    """
    global camdb_win
    
    # If it's already open & visible, just bring it forward
    if camdb_win:
        if camdb_win.isVisible():
            camdb_win.raise_()
            camdb_win.activateWindow()
            return
        else:
            camdb_win.show()
            camdb_win.raise_()
            camdb_win.activateWindow()
            return
    
    # Otherwise, create it anew
    parent = hou.ui.mainQtWindow()
    camdb_win = CamDBPanel(parent)
    camdb_win.setWindowFlags(QtCore.Qt.Window)
    camdb_win.show()

# Execute immediately when the shelf tool is clicked
show_camdb_floating()