import time
from kubernetes import client, config, watch
import logging

logging.basicConfig(level=logging.INFO)

def main():
    config.load_kube_config()
    v1 = client.CoreV1Api()
    w = watch.Watch()
    for event in w.stream(v1.list_pod_for_all_namespaces):
        pod = event["object"]
        if event["type"] == "MODIFIED":
            print(f"Checking {pod.metadata.name} for abrupt container stops...")

if __name__ == "__main__":
    main()