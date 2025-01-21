# wdmon - Kubernetes Workload Disruption Monitor

This tool monitors Kubernetes Pods, to detect containers terminated by SIGKILL rather than the graceful SIGTERM, helping identify unexpected disruptions in workloads. The goal is to distinguish between unexpected terminations due to OOM and terminations due to termination grace period expiration.

## How to test
Use the attached wdtest.yaml to run the test Deployment:

```
kubectl create -f wdtest.yaml
```

Test SIGTERM due to nongraceful termination by terminating the pod created by the Deployment (using kubectl):
```
kubectul delete pod -l app=wdtest
```

Test SIGTERM due to OOM by triggering memory-intesive logic in the container, by creating a file via executing a 'touch' command:
```
kubectl exec deploy/wdtest -- touch /tmp/oom
```