# Deploying MacroScope to Google Kubernetes Engine (GKE)

This puts the same app that runs in Docker Compose onto a GKE cluster in Sydney
(`australia-southeast1`). Nothing in the code changes: the same images, configured with
environment variables.

```
browser ──HTTPS──► Google load balancer (the Ingress, 60-ingress.yaml) at https://<ip>.nip.io
                     ├─ /api/meals      ─► meal-logging     (2-6 pods) ─► meal-db (StatefulSet + disk) + redis
                     ├─ /api/nutrients  ─► nutrient-calc    (2-6 pods) ─► nutrient-db
                     ├─ /api/gaps       ─► gap-analysis     (2-4 pods) ─► gap-db
                     ├─ /api/recommend  ─► food-recommender (2-4 pods) ─► recommender-db
                     └─ /               ─► frontend         (2 pods)
         all spread across 2 identical VMs (the cluster's nodes)
```

| File | What it makes |
|---|---|
| `00-namespace.yaml` | the `macroscope` namespace everything lives in |
| `10-databases.yaml` | the 4 Postgres databases, each a StatefulSet with its own 5 GB disk |
| `20-redis.yaml` | Redis, the search cache |
| `30-services.yaml` | the 4 services: Deployments (2 pods each, rolling updates, health checks) and Services |
| `40-frontend.yaml` | the website |
| `50-autoscaling.yaml` | autoscalers that add pods when CPU gets busy |
| `60-ingress.yaml` | the HTTPS load balancer, its certificate, and the http-to-https redirect |

The settings and secrets aren't in these files. They're made with commands below (step 5), so no
passwords end up in git.

**It costs money while it runs**: about A$5-7 a day for the 2 VMs, the load balancer and the disks
(from your Google Cloud credits). "Pausing it" at the end shows how to turn it off between sessions.

All commands are for **PowerShell**, run from the project folder.

## 0. Once: install the Google Cloud CLI and log in

```powershell
# Install the Google Cloud CLI (gcloud). Close and reopen PowerShell afterwards.
#   install  install a package from winget, Windows' package manager
winget install Google.CloudSDK

# Log in with your Google account (opens a browser)
gcloud auth login

# Use your project for every gcloud command from now on
gcloud config set project just-tracer-294608

# Add the plugin kubectl needs to log in to GKE clusters
gcloud components install gke-gcloud-auth-plugin
```

## 1. Turn on the Google Cloud services we use

```powershell
# Kubernetes Engine, Artifact Registry (where our images are stored) and Compute Engine (VMs, disks, IPs)
gcloud services enable container.googleapis.com artifactregistry.googleapis.com compute.googleapis.com
```

## 2. Build the images and upload them

```powershell
# Where the images go (a private Docker registry in our project, in Sydney)
$REG = "australia-southeast1-docker.pkg.dev/just-tracer-294608/macroscope"

# Make the registry (only once)
#   --repository-format=docker  it holds Docker images
#   --location                  the region it lives in
gcloud artifacts repositories create macroscope --repository-format=docker --location=australia-southeast1

# Let Docker log in to it with your gcloud login (only once)
gcloud auth configure-docker australia-southeast1-docker.pkg.dev

# Build each service with its version baked in, and push it
#   --build-arg APP_VERSION=1.0.0  the version the image reports at /version (and in the website footer)
#   -t                             the image's name and tag (the tag is the version)
foreach ($s in "meal-logging", "nutrient-calc", "gap-analysis", "food-recommender") {
    docker build --build-arg APP_VERSION=1.0.0 -t "$REG/${s}:1.0.0" "services/$s"
    docker push "$REG/${s}:1.0.0"
}
docker build -t "$REG/frontend:1.0.0" frontend
docker push "$REG/frontend:1.0.0"
```

## 3. Make the cluster (the 2 VMs)

```powershell
# A GKE cluster with 2 identical VMs (nodes). Takes about 5 minutes.
#   --zone          one zone in Sydney (a zonal cluster's management fee is covered by Google's free tier)
#   --num-nodes 2   two VMs, made from the same template, so the second is a copy of the first
#   --machine-type  e2-standard-2: 2 vCPUs and 8 GB of memory each
#   --disk-size     each VM's own boot disk, in GB
gcloud container clusters create macroscope --zone australia-southeast1-a --num-nodes 2 --machine-type e2-standard-2 --disk-size 30

# Point kubectl at the new cluster (the create command usually does this already)
gcloud container clusters get-credentials macroscope --zone australia-southeast1-a

# Check: you should see 2 nodes, both "Ready"
kubectl get nodes
```

## 4. Reserve the IP address and fill in the domain

```powershell
# A fixed public IP address for the load balancer
#   --global  load balancer IPs for HTTPS are global
gcloud compute addresses create macroscope-ip --global

# Show it, e.g. 34.120.5.6
$IP = gcloud compute addresses describe macroscope-ip --global --format="value(address)"
$IP

# Our web address is that IP with dashes, plus .nip.io (34.120.5.6 -> 34-120-5-6.nip.io).
# Put it into the certificate in 60-ingress.yaml.
#   -Raw and WriteAllText keep the file exactly as it was apart from the domain (Set-Content in
#   Windows PowerShell would switch it to Windows line endings and add an invisible marker at the start)
$DOMAIN = ($IP -replace '\.', '-') + ".nip.io"
$file = "$PWD/k8s/60-ingress.yaml"
[IO.File]::WriteAllText($file, ((Get-Content $file -Raw) -replace 'REPLACE-WITH-IP\.nip\.io', $DOMAIN))
$DOMAIN
```

## 5. Settings and secrets

```powershell
# The namespace first, because the settings go in it
kubectl apply -f k8s/00-namespace.yaml

# Read the Web API key from .env, so it's copied exactly (a stray character breaks every login)
$KEY = ((Get-Content .env) | Where-Object { $_ -match '^GOOGLE_API_KEY=' }) -replace '^GOOGLE_API_KEY=', ''

# Settings every service reads (not secret). The project and Web API key are the same ones as in .env.
#   create configmap      make a ConfigMap (settings) object
#   --from-literal=K=V    one setting
kubectl create configmap macroscope-config -n macroscope `
  --from-literal=GOOGLE_PROJECT_ID=just-tracer-294608 `
  --from-literal=GOOGLE_API_KEY=$KEY `
  --from-literal=LOG_LEVEL=INFO

# (To change a setting later: run the same command with --dry-run=client -o yaml | kubectl apply -f -
#  on the end, then restart the services so they read it: kubectl rollout restart deployment -n macroscope)

# Secrets: a new random JWT secret and database passwords, just for the cluster
#   python -c ...  prints 32 random hex characters
function New-Password { python -c "import secrets; print(secrets.token_hex(16))" }
kubectl create secret generic macroscope-secrets -n macroscope `
  --from-literal=jwt-secret=$(python -c "import secrets; print(secrets.token_hex(32))") `
  --from-literal=meal-db-password=$(New-Password) `
  --from-literal=nutrient-db-password=$(New-Password) `
  --from-literal=gap-db-password=$(New-Password) `
  --from-literal=recommender-db-password=$(New-Password)

# Each database's init.sql (the tables), so Postgres can run it the first time it starts
#   --from-file=init.sql=<path>  put that file in the ConfigMap, named init.sql
kubectl create configmap meal-db-init -n macroscope --from-file=init.sql=services/meal-logging/db/init.sql
kubectl create configmap nutrient-db-init -n macroscope --from-file=init.sql=services/nutrient-calc/db/init.sql
kubectl create configmap gap-db-init -n macroscope --from-file=init.sql=services/gap-analysis/db/init.sql
kubectl create configmap recommender-db-init -n macroscope --from-file=init.sql=services/food-recommender/db/init.sql
```

## 6. Start everything

```powershell
# Create (or update) everything in the k8s folder
#   -f k8s/  every .yaml file in the folder, in name order
kubectl apply -f k8s/

# Watch the pods start (Ctrl+C to stop watching). After a minute or two they should all be
# "Running" and "1/1" ready.
#   -w  keep watching for changes
kubectl get pods -n macroscope -w
```

The load balancer takes 5-10 minutes to appear. `kubectl get ingress -n macroscope` shows its IP
once it's ready.

## 7. Copy the food data (and demo users) into the cloud databases

The quickest way is to copy the local databases, which already have the 1,030,440 rows of food
data, the demo users' meals and your own. With Docker Compose running locally:

```powershell
# For each database: dump it from the local container, copy the file into the cluster's database
# pod, and load it there.
#   pg_dump -Fc           dump in Postgres's own compressed format
#   kubectl cp            copy a file into a pod
#   pg_restore --clean    drop the empty tables init.sql made, and load the dumped ones
#   --if-exists           don't complain about anything that isn't there
#   --no-owner            make everything belong to the cluster's database user
$dbs = @(("meal-db", "meal", "meal_db"), ("nutrient-db", "nutrient", "nutrient_db"),
         ("gap-db", "gap", "gap_db"), ("recommender-db", "recommender", "recommender_db"))

# Work in the Temp folder. kubectl cp on Windows reads the "C:" in a full path as a pod name,
# so the files have to be named without a drive letter.
Push-Location $env:TEMP
foreach ($d in $dbs) {
    $pod, $user, $db = $d
    docker compose -f "$HOME/Documents/INFS3208/docker-compose.yml" exec -T $pod pg_dump -U $user -Fc $db -f /tmp/$db.dump
    docker compose -f "$HOME/Documents/INFS3208/docker-compose.yml" cp "${pod}:/tmp/$db.dump" "$db.dump"
    kubectl cp "$db.dump" "macroscope/${pod}-0:/tmp/$db.dump"
    kubectl exec -n macroscope "${pod}-0" -- pg_restore -U $user -d $db --clean --if-exists --no-owner /tmp/$db.dump
}
Pop-Location

# Check: this should say 864594, the same as locally
kubectl exec -n macroscope nutrient-db-0 -- psql -U nutrient -d nutrient_db -c "SELECT count(*) FROM food_nutrient"
```

(Or load it from scratch with the loader: `kubectl port-forward` each database to your machine and
run `docker compose run --rm etl` with the database addresses pointed at the forwarded ports.)

## 8. Google sign-in

In the Google Cloud console, under **Identity Platform**:

1. **Settings > Security > Authorized domains > Add domain**: add your `$DOMAIN`
   (like `34-120-5-6.nip.io`). Google only lets people log in from listed sites.
2. **Providers > Add a provider > Google**: turn it on and save. This makes the website's
   "Continue with Google" button work, on the cloud site and on localhost.

## 9. Turn on HTTPS only

Google issues the certificate once the load balancer is up and the domain points at it, which
takes 15-60 minutes. Until then, use `http://<domain>`.

```powershell
# Check the certificate. Wait until "Certificate Status" says Active.
kubectl describe managedcertificate macroscope-cert -n macroscope

# Then send http:// visitors to https://
#   annotate  add a setting to the Ingress that points it at the redirect in 60-ingress.yaml
kubectl annotate ingress macroscope -n macroscope networking.gke.io/v1beta1.FrontendConfig=macroscope-https-redirect
```

Open **https://&lt;your domain&gt;**. Log in as a demo user, or as yourself.

## Demo commands

```powershell
# Everything that's running, and which node each pod is on
#   -o wide  show more columns, including the node
kubectl get pods -n macroscope -o wide

# Scaling: run 4 copies of nutrient-calc (the autoscaler can also do this by itself)
kubectl scale deployment nutrient-calc -n macroscope --replicas=4

# Load test against the cloud, and watch the autoscaler add pods in another window
#   -e GATEWAY_URL=...  send the load test to the cloud site instead of the local gateway
docker compose run --rm -e GATEWAY_URL=https://$DOMAIN loadtest --users 40 --seconds 120
kubectl get hpa -n macroscope --watch

# Pod failure: delete a pod. Kubernetes starts a new one, and the other copy keeps serving.
kubectl delete pod -n macroscope -l app=meal-logging --wait=false
kubectl get pods -n macroscope -l app=meal-logging -w

# VM failure: every service has one pod on each of the 2 VMs, so losing a VM doesn't take
# anything down. "Drain" a VM to pretend it has failed: Kubernetes moves everything off it, and the
# copies on the other VM keep the site working. The databases move with their disks (about a
# minute for any that were on that VM).
#   get nodes                     list the 2 VMs; copy one name for the next commands
#   drain                         stop using that VM and move its pods to the other one
#   --ignore-daemonsets           leave Google's own per-VM helpers alone
#   --delete-emptydir-data        allow pods with temporary scratch space to be moved
kubectl get nodes
kubectl drain <node-name> --ignore-daemonsets --delete-emptydir-data
kubectl get pods -n macroscope -o wide
# Bring the VM back into use (new pods can go on it again)
kubectl uncordon <node-name>

# Rolling update: build and push version 1.1.0 of a service, then switch to it. Pods are
# replaced one at a time, and the website footer shows the new version.
docker build --build-arg APP_VERSION=1.1.0 -t "$REG/nutrient-calc:1.1.0" services/nutrient-calc
docker push "$REG/nutrient-calc:1.1.0"
kubectl set image deployment/nutrient-calc -n macroscope nutrient-calc="$REG/nutrient-calc:1.1.0"
kubectl rollout status deployment/nutrient-calc -n macroscope

# Rollback: go back to the version before
kubectl rollout undo deployment/nutrient-calc -n macroscope
kubectl rollout history deployment/nutrient-calc -n macroscope
```

## Pausing it (to save credits)

```powershell
# Turn the 2 VMs off. The databases' disks, the IP address and the load balancer stay (a small
# daily cost), so everything comes back as it was.
#   resize --num-nodes 0  run no VMs
gcloud container clusters resize macroscope --zone australia-southeast1-a --num-nodes 0

# Turn them back on (pods start again within a few minutes)
gcloud container clusters resize macroscope --zone australia-southeast1-a --num-nodes 2
```

## Deleting it all (when the assignment is marked)

```powershell
# The cluster, its VMs and load balancer
gcloud container clusters delete macroscope --zone australia-southeast1-a

# The IP address and the images
gcloud compute addresses delete macroscope-ip --global
gcloud artifacts repositories delete macroscope --location=australia-southeast1

# Check no database disks were left behind (delete any listed with gcloud compute disks delete)
gcloud compute disks list
```
