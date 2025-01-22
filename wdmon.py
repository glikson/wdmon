import time
from kubernetes import client, config, watch
import logging
from flask import Flask, render_template, send_from_directory
from threading import Thread
from collections import defaultdict
import datetime
import sys
from typing import Optional

# Initialize logger first
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)

app = Flask(__name__, static_url_path='/static', static_folder='static')

# Store disruptions in memory
disruptions = defaultdict(list)

def is_duplicate_event(deployment_name: str, pod_name: str, window_seconds: int = 5) -> Optional[dict]:
    """Check if there's a recent event for the same pod within the time window."""
    if not disruptions[deployment_name]:
        return None
    
    current_time = datetime.datetime.now()
    recent_events = [
        d for d in disruptions[deployment_name]
        if d['pod'] == pod_name and
        (current_time - datetime.datetime.strptime(d['timestamp'], '%Y-%m-%d %H:%M:%S')).total_seconds() <= window_seconds
    ]
    
    return recent_events[0] if recent_events else None

def track_disruption(deployment_name, container_name, pod_name, reason, timestamp):
    # Check for recent events for the same pod
    recent_event = is_duplicate_event(deployment_name, pod_name)
    
    if recent_event:
        # If recent event exists, log it but don't track
        logger.info(f"Skipping duplicate event for pod {pod_name} (previous event: {recent_event['reason']} at {recent_event['timestamp']})")
        return
    
    msg = f"Container {container_name} in {pod_name} exited with 137 ({reason})"
    print(msg)  # Print to stdout
    logger.info(msg)  # Log to logger
    # Store timestamp as string immediately
    disruptions[deployment_name].append({
        'container': container_name,
        'pod': pod_name,
        'reason': reason,
        'timestamp': timestamp.strftime('%Y-%m-%d %H:%M:%S')
    })

def get_deployment_for_pod(v1, pod):
    owner_references = pod.metadata.owner_references or []
    for owner in owner_references:
        if owner.kind == 'ReplicaSet':
            rs = client.AppsV1Api().read_namespaced_replica_set(
                owner.name, pod.metadata.namespace)
            if rs.metadata.owner_references:
                for rs_owner in rs.metadata.owner_references:
                    if rs_owner.kind == 'Deployment':
                        return rs_owner.name
    return None

def watch_pods():
    while True:
        try:
            config.load_incluster_config()
            logger.info("Using in-cluster configuration")
        except config.ConfigException:
            config.load_kube_config()
            logger.info("Using local kubeconfig")

        v1 = client.CoreV1Api()
        w = watch.Watch()
        
        try:
            logger.info("Starting to watch pods in default namespace")
            for event in w.stream(v1.list_namespaced_pod, namespace='default'):
                if event["type"] == "MODIFIED":
                    pod = event["object"]
                    deployment_name = get_deployment_for_pod(v1, pod)
                    if deployment_name:
                        for cs in pod.status.container_statuses or []:
                            if cs.state.terminated and cs.state.terminated.exit_code == 137:
                                timestamp = datetime.datetime.now()
                                if cs.state.terminated.reason == "OOMKilled":
                                    track_disruption(deployment_name, cs.name, pod.metadata.name, 
                                                   "OOMKilled", timestamp)
                                elif (cs.state.terminated.reason == "Error" and 
                                      pod.metadata.deletion_timestamp and 
                                      pod.metadata.deletion_grace_period_seconds == 0):
                                    track_disruption(deployment_name, cs.name, pod.metadata.name,
                                                   "Non-graceful termination", timestamp)
        except Exception as e:
            logger.error(f"Error watching pods: {e}")
            time.sleep(5)

@app.route('/')
def index():
    apps_v1 = client.AppsV1Api()
    deployments = apps_v1.list_namespaced_deployment(namespace='default')
    stats = []
    for dep in deployments.items:
        dep_disruptions = disruptions[dep.metadata.name]
        
        # Find the latest disruption timestamp
        if dep_disruptions:
            # Compare string timestamps (they're in sortable format)
            last_disruption = max(d['timestamp'] for d in dep_disruptions)
        else:
            last_disruption = None

        stats.append({
            'name': dep.metadata.name,
            'oom_count': sum(1 for d in dep_disruptions if d['reason'] == 'OOMKilled'),
            'termination_count': sum(1 for d in dep_disruptions if d['reason'] == 'Non-graceful termination'),
            'total_count': len(dep_disruptions),
            'last_disruption': last_disruption,
            'status': 'Disrupted' if dep_disruptions else 'Healthy'
        })
    return render_template('index.html', stats=stats)

@app.route('/deployment/<name>')
def deployment_details(name):
    disruptions_list = sorted(
        disruptions[name],
        key=lambda x: x['timestamp'],
        reverse=True
    )
    # No need to convert timestamps as they're already strings
    return {'disruptions': disruptions_list}

@app.route('/healthz')
def healthz():
    return {'status': 'ok'}

def main():
    try:
        # Start the pod watcher in a separate thread
        watch_thread = Thread(target=watch_pods, daemon=True)
        watch_thread.start()
        
        logger.info("Starting Flask server on port 8080...")
        # Use production server instead of development server
        from waitress import serve
        serve(app, host='0.0.0.0', port=8080)
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()