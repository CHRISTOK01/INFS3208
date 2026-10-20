# Kubernetes files for GKE

> Part of the MacroScope docs. Start at the [main README](../README.md), which also lists where everything else is.

How to deploy with these, step by step, is in the [main README](../README.md). `kubectl apply -f k8s/`
(step 10 there) applies them all, in name order.

| File | What it makes |
|---|---|
| `00-namespace.yaml` | the `macroscope` namespace everything lives in |
| `10-databases.yaml` | the 4 Postgres databases, each a StatefulSet with its own 5 GB disk |
| `20-redis.yaml` | Redis, the search cache |
| `30-services.yaml` | the 4 services: Deployments (2 pods each, rolling updates, health checks) and Services |
| `40-frontend.yaml` | the website |
| `50-autoscaling.yaml` | autoscalers that add pods when CPU gets busy |
| `60-ingress.yaml` | the HTTPS load balancer, its certificate, and the http-to-https redirect |

Three things in them are specific to a deployment, and the README's commands fill them in:

- the image registry in `30-services.yaml` and `40-frontend.yaml`, which contains the project ID
  (step 6)
- the domain in the certificate in `60-ingress.yaml` (step 8)
- the settings and secrets, which aren't in these files at all, so no passwords end up in git
  (step 9)
