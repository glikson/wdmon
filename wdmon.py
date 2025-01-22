import time
from kubernetes import client, config, watch
import logging
from flask import Flask, render_template, send_from_directory
from threading import Thread, Event
from collections import defaultdict
import datetime
import sys
from typing import Optional, Dict, List
import signal
from waitress.server import create_server
import json
import os

# Initialize logger first
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)

app = Flask(__name__, static_url_path='/static', static_folder='static')

def is_running_in_kubernetes():
    """Check if running inside Kubernetes by looking for service account token."""
    return os.path.exists('/var/run/secrets/kubernetes.io/serviceaccount/token')

class EventStore:
    def __init__(self, data_dir: str = None):
        if data_dir is None:
            # Use current directory for local development, /data for kubernetes
            data_dir = '/data' if is_running_in_kubernetes() else '/tmp'
            logger.info(f"Using {data_dir} directory for persistence")
        
        self.data_file = os.path.join(data_dir, 'disruptions.json')
        self.disruptions: Dict[str, List[dict]] = defaultdict(list)
        self.load_data()

    def load_data(self):
        """Load disruption data from file, ignore records with unrecognized fields."""
        if not os.path.exists(self.data_file):
            return

        try:
            with open(self.data_file, 'r') as f:
                data = json.load(f)
                if not isinstance(data, dict) or 'disruptions' not in data:
                    return
                
                # Load only records with expected fields
                expected_fields = {'container', 'pod', 'reason', 'timestamp'}
                for deployment, events in data['disruptions'].items():
                    valid_events = [
                        event for event in events
                        if isinstance(event, dict) and all(f in event for f in expected_fields)
                    ]
                    if valid_events:
                        self.disruptions[deployment].extend(valid_events)
                
                logger.info(f'Loaded {sum(len(v) for v in self.disruptions.values())} events')
        except Exception as e:
            logger.error(f'Error loading disruption data: {e}')

    def save_data(self):
        """Save disruption data to file."""
        try:
            data = {'disruptions': dict(self.disruptions)}
            os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
            with open(self.data_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f'Error saving disruption data: {e}')

    def add_event(self, deployment_name: str, event: dict):
        """Add new event and persist to disk."""
        self.disruptions[deployment_name].append(event)
        self.save_data()

    def get_events(self, deployment_name: str) -> List[dict]:
        """Get events for a deployment."""
        return self.disruptions[deployment_name]

# Initialize event store
event_store = EventStore()

# Add global flag for graceful shutdown
shutdown_requested = False

# Add shutdown event
shutdown_event = Event()

def signal_handler(signum, frame):
    """Handle termination signals gracefully."""
    global shutdown_requested
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    shutdown_requested = True
    shutdown_event.set()

def is_duplicate_event(deployment_name: str, pod_name: str, window_seconds: int = 5) -> Optional[dict]:
    """Check if there's a recent event for the same pod within the time window."""
    if not event_store.get_events(deployment_name):
        return None
    
    current_time = datetime.datetime.now()
    recent_events = [
        d for d in event_store.get_events(deployment_name)
        if d['pod'] == pod_name and
        (current_time - datetime.datetime.strptime(d['timestamp'], '%Y-%m-%d %H:%M:%S')).total_seconds() <= window_seconds
    ]
    
    return recent_events[0] if recent_events else None

def track_disruption(deployment_name, container_name, pod_name, reason, timestamp):
    # Check for recent events for the same pod
    recent_event = is_duplicate_event(deployment_name, pod_name)
    
    if recent_event:
        logger.info(f"Skipping duplicate event for pod {pod_name}")
        return
    
    msg = f"Container {container_name} in {pod_name} exited with 137 ({reason})"
    print(msg)
    logger.info(msg)
    
    event = {
        'container': container_name,
        'pod': pod_name,
        'reason': reason,
        'timestamp': timestamp.strftime('%Y-%m-%d %H:%M:%S')
    }
    
    event_store.add_event(deployment_name, event)

def get_workload_info(v1, pod):
    """Get workload info from pod's owner references."""
    owner_references = pod.metadata.owner_references or []
    for owner in owner_references:
        if owner.kind == 'ReplicaSet':
            rs = client.AppsV1Api().read_namespaced_replica_set(
                owner.name, pod.metadata.namespace)
            if rs.metadata.owner_references:
                for rs_owner in rs.metadata.owner_references:
                    if rs_owner.kind == 'Deployment':
                        return {'type': 'Deployment', 'name': rs_owner.name, 'namespace': pod.metadata.namespace}
        elif owner.kind == 'StatefulSet':
            return {'type': 'StatefulSet', 'name': owner.name, 'namespace': pod.metadata.namespace}
        elif owner.kind == 'DaemonSet':
            return {'type': 'DaemonSet', 'name': owner.name, 'namespace': pod.metadata.namespace}
    return None

def init_kubernetes_client():
    """Initialize Kubernetes client configuration."""
    try:
        config.load_incluster_config()
        logger.info("Using in-cluster configuration")
    except config.ConfigException:
        config.load_kube_config()
        logger.info("Using local kubeconfig")
    return client.CoreV1Api()

def watch_pods(v1):
    while not shutdown_requested:
        w = watch.Watch()
        try:
            logger.info("Starting to watch pods in all namespaces")
            for event in w.stream(v1.list_pod_for_all_namespaces):
                if shutdown_requested:
                    logger.info("Shutdown requested, stopping pod watch")
                    break
                if event["type"] == "MODIFIED":
                    pod = event["object"]
                    workload = get_workload_info(v1, pod)
                    if workload:
                        for cs in pod.status.container_statuses or []:
                            if cs.state.terminated and cs.state.terminated.exit_code == 137:
                                timestamp = datetime.datetime.now()
                                if cs.state.terminated.reason == "OOMKilled":
                                    track_disruption(f"{workload['namespace']}/{workload['type']}/{workload['name']}", 
                                                   cs.name, pod.metadata.name, "OOMKilled", timestamp)
                                elif (cs.state.terminated.reason == "Error" and 
                                      pod.metadata.deletion_timestamp and 
                                      pod.metadata.deletion_grace_period_seconds == 0):
                                    track_disruption(f"{workload['namespace']}/{workload['type']}/{workload['name']}", 
                                                   cs.name, pod.metadata.name, "Non-graceful termination", timestamp)
        except Exception as e:
            logger.error(f"Error watching pods: {e}")
            time.sleep(5)

@app.route('/')
def index():
    apps_v1 = client.AppsV1Api()
    stats = []
    
    for ns in client.CoreV1Api().list_namespace().items:
        namespace = ns.metadata.name
        
        # Get all workload types
        for workload_type, api_func in {
            'Deployment': apps_v1.list_namespaced_deployment,
            'StatefulSet': apps_v1.list_namespaced_stateful_set,
            'DaemonSet': apps_v1.list_namespaced_daemon_set
        }.items():
            for workload in api_func(namespace=namespace).items:
                workload_key = f"{namespace}/{workload_type}/{workload.metadata.name}"
                stats.append(get_workload_stats(workload_key, namespace, workload_type, workload.metadata.name))
    
    return render_template('index.html', stats=sorted(stats, key=lambda x: (x['namespace'], x['type'], x['workload_name'])))

def get_workload_stats(workload_key, namespace, workload_type, workload_name):
    """Get disruption stats for a workload."""
    dep_disruptions = event_store.get_events(workload_key)
    last_disruption = max((d['timestamp'] for d in dep_disruptions), default=None) if dep_disruptions else None
    
    return {
        'key': workload_key,
        'namespace': namespace,
        'type': workload_type,
        'workload_name': workload_name,
        'oom_count': sum(1 for d in dep_disruptions if d['reason'] == 'OOMKilled'),
        'termination_count': sum(1 for d in dep_disruptions if d['reason'] == 'Non-graceful termination'),
        'total_count': len(dep_disruptions),
        'last_disruption': last_disruption,
        'status': 'Disrupted' if dep_disruptions else 'Healthy'
    }

@app.route('/workload/<path:key>')
def workload_details(key):
    """Handle workload details with namespace/type/name path."""
    disruptions_list = sorted(
        event_store.get_events(key),
        key=lambda x: x['timestamp'],
        reverse=True
    )
    return {'disruptions': disruptions_list}

@app.route('/healthz')
def healthz():
    return {'status': 'ok'}

def run_server(server):
    """Run the server in a separate thread."""
    try:
        server.run()
    except Exception as e:
        if not shutdown_requested:
            logger.error(f"Server error: {e}")
    finally:
        logger.info("Server thread stopped")

def main():
    try:
        # Initialize Kubernetes client
        v1_client = init_kubernetes_client()
        
        # Set up signal handlers
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
        
        # Start the pod watcher in a separate thread
        watch_thread = Thread(target=watch_pods, args=(v1_client,), daemon=True)
        watch_thread.start()
        
        # Start the server in a separate thread
        logger.info("Starting Flask server on port 8080...")
        server = create_server(app, host='0.0.0.0', port=8080)
        server_thread = Thread(target=run_server, args=(server,), daemon=True)
        server_thread.start()
        
        # Wait for shutdown signal
        shutdown_event.wait()
        logger.info("Shutdown complete")
        
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()