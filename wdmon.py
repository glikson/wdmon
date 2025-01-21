import time
from kubernetes import client, config, watch
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    try:
        config.load_incluster_config()
        logger.info("Loaded in-cluster config")
    except config.ConfigException:
        config.load_kube_config()
        logger.info("Loaded kube config")

    v1 = client.CoreV1Api()
    w = watch.Watch()
    
    logger.info("Starting to watch pods")
    while True:
        try:
            for event in w.stream(v1.list_pod_for_all_namespaces):
                logger.debug(f"Received event type: {event['type']} for pod: {event['object'].metadata.name}")
                pod = event["object"]
                if event["type"] == "MODIFIED":
                    for cs in pod.status.container_statuses or []:
                        if cs.state.terminated and cs.state.terminated.exit_code == 137:
                            msg = None
                            if cs.state.terminated.reason == "OOMKilled":
                                msg = f"Container {cs.name} in {pod.metadata.name} exited with 137 (OOMKilled)"
                            elif (cs.state.terminated.reason == "Error" and 
                                  pod.metadata.deletion_timestamp and 
                                  pod.metadata.deletion_grace_period_seconds == 0):
                                msg = f"Container {cs.name} in {pod.metadata.name} exited with 137 (Error) - likely due to non-graceful termination"
                            if msg:
                                logger.info(msg)
                                print(msg)
        except Exception as e:
            logger.error(f"Error watching pods: {e}")
            time.sleep(5)  # Wait before retrying
            continue

if __name__ == "__main__":
    main()