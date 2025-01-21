import time
from kubernetes import client, config, watch

def main():
    config.load_kube_config()
    v1 = client.CoreV1Api()
    w = watch.Watch()
    for event in w.stream(v1.list_pod_for_all_namespaces):
#        print(".", end="", flush=True)
        pod = event["object"]
        if event["type"] == "MODIFIED":
            for cs in pod.status.container_statuses or []:
                # Check that the container has been SIGKILLed
                if cs.state.terminated and cs.state.terminated.exit_code == 137:
                    if cs.state.terminated.reason == "OOMKilled":
                        print(f"Container {cs.name} in {pod.metadata.name} exited with 137 (OOMKilled).")
                    elif cs.state.terminated.reason == "Error":
                        # If the pod has deletion time and deletion grace period of 0, print a message. 
                        # Otherwise ignore (non-graceful termination involves several Pod updates).
                        # TODO: This is a heuristic and may not work in all cases.
                        if pod.metadata.deletion_timestamp and pod.metadata.deletion_grace_period_seconds == 0:
                            print(f"Container {cs.name} in {pod.metadata.name} exited with 137 (Error) - likely due to non-graceful termination.")
 
if __name__ == "__main__":
    main()