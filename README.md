# wdmon - Kubernetes Workload Disruption Monitor

This tool monitors Kubernetes Pods, to detect containers terminated by SIGKILL rather than the graceful SIGTERM, helping identify unexpected disruptions in workloads. The goal is to distinguish between unexpected terminations due to OOM and terminations due to termination grace period expiration.

## How to test

1. Run wdmon:
```
python wdmon.py
```

1. Use the attached wdtest.yaml to run the test Deployment:

```
kubectl create -f wdtest.yaml
```

1. Test SIGTERM due to nongraceful termination by terminating the pod created by the Deployment (using kubectl):
```
kubectl delete pod -l app=wdtest
```
Expected output of wdmon:
```
Container test-container in wdtest-854bd59d47-ngcg9 exited with 137 (OOMKilled).
```

Test SIGTERM due to OOM by triggering memory-intesive logic in the container, by creating a file via executing a 'touch' command:
```
kubectl exec deploy/wdtest -- touch /tmp/oom
```
Expected output of wdmon:
```
Container test-container in wdtest-854bd59d47-pl8qz exited with 137 (OOMKilled).
```
