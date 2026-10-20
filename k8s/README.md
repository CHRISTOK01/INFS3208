# Deploying MacroScope to Google Kubernetes Engine (GKE)

This is how MacroScope was deployed to its GKE cluster in Sydney (`australia-southeast1`), where it
runs live at https://34-120-54-167.nip.io. It's the same app that runs in Docker Compose. Nothing in
the code changes: the same images, configured with environment variables. Every command we ran is
here, in order, with what it does.

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

**Estimated monthly cost**: about A$150-210 a month if it's left running all the time (A$5-7 a day),
and less when it's paused between sessions (the disks, the IP address and the load balancer still
cost a little while the VMs are off).

All commands are for **PowerShell**, run from the project folder.

**Before you start, set the app up on your computer** (["Setting it up on your computer" in the
main README](../README.md)): the `.env` file, Google login, and the food data and demo users loaded
into the local databases. This guide reads the Web API key from `.env` (step 5) and copies the data
from the local databases into the cloud ones (step 7).

**The project ID `<your-project-id>` appears throughout this guide.** To follow it in a different
Google Cloud project, replace it with that project's ID, including in the registry path `$REG` (step 2), which contains it, and in
the image names in `30-services.yaml` and `40-frontend.yaml`.

## 0. Once: install the Google Cloud CLI and log in

```powershell
# Install the Google Cloud CLI (gcloud). Close and reopen PowerShell afterwards.
#   install  install a package from winget, Windows' package manager
winget install Google.CloudSDK

# Log in with your Google account (opens a browser)
gcloud auth login

# Use your project for every gcloud command from now on
#   config set project <id>  save <id> as the default project
gcloud config set project <your-project-id>

# Add the plugin kubectl needs to log in to GKE clusters
#   components install <name>  add an optional part of the Google Cloud CLI
gcloud components install gke-gcloud-auth-plugin
```

## 1. Turn on the Google Cloud services we use

```powershell
# Kubernetes Engine, Artifact Registry (where our images are stored) and Compute Engine (VMs, disks, IPs)
#   services enable <apis>  switch those Google Cloud services on for the project
gcloud services enable container.googleapis.com artifactregistry.googleapis.com compute.googleapis.com
```

## 2. Build the images and upload them

```powershell
# Where the images go (a private Docker registry in our project, in Sydney)
$REG = "australia-southeast1-docker.pkg.dev/<your-project-id>/macroscope"

# Make the registry (only once)
#   --repository-format=docker  it holds Docker images
#   --location                  the region it lives in
gcloud artifacts repositories create macroscope --repository-format=docker --location=australia-southeast1

# Let Docker log in to it with your gcloud login (only once)
#   auth configure-docker <host>  tell Docker to use gcloud's login for that registry address
gcloud auth configure-docker australia-southeast1-docker.pkg.dev

# The version of each image. These must match the image tags in 30-services.yaml and
# 40-frontend.yaml, or Kubernetes can't find the images.
#   @{ name = value; ... }  a lookup table (a "hashtable")
$versions = @{ "meal-logging" = "1.0.1"; "nutrient-calc" = "1.0.0"; "gap-analysis" = "1.0.1"; "food-recommender" = "1.0.2" }

# Build each service with its version baked in, and push (upload) it
#   foreach ($s in $versions.Keys)  repeat for each of the 4 services
#   --build-arg APP_VERSION=<v>     the version the image reports at /version (and in the website footer)
#   -t                              the image's name and tag (the tag is the version)
#   docker push                     upload the image to the registry
foreach ($s in $versions.Keys) {
    $v = $versions[$s]
    docker build --build-arg APP_VERSION=$v -t "$REG/${s}:$v" "services/$s"
    docker push "$REG/${s}:$v"
}
# The website the same way (it has no /version, so no --build-arg)
docker build -t "$REG/frontend:1.0.6" frontend
docker push "$REG/frontend:1.0.6"
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
#   get-credentials <name>  save the cluster's address and login for kubectl
#   --zone                  where the cluster is
gcloud container clusters get-credentials macroscope --zone australia-southeast1-a

# Check: you should see 2 nodes, both "Ready"
kubectl get nodes
```

(Our cluster's VMs are in a node pool we called `app-pool`, so they're named
`gke-macroscope-app-pool-...`. We made it with `gcloud container node-pools create app-pool --cluster
macroscope --zone australia-southeast1-a --num-nodes 2 --machine-type e2-standard-2 --disk-size 30`,
moved the pods over with `kubectl drain`, and deleted Google's `default-pool`.)

## 4. Reserve the IP address and fill in the domain

```powershell
# A fixed public IP address for the load balancer
#   --global  load balancer IPs for HTTPS are global
gcloud compute addresses create macroscope-ip --global

# Show it, e.g. 34.120.5.6
#   describe <name>                 show the address's details
#   --format="value(address)"       print only the IP itself
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
#   apply -f <file>  create (or update) what the file describes
kubectl apply -f k8s/00-namespace.yaml

# Read the Web API key from .env, so it's copied exactly (a stray character breaks every login)
$KEY = ((Get-Content .env) | Where-Object { $_ -match '^GOOGLE_API_KEY=' }) -replace '^GOOGLE_API_KEY=', ''

# Settings every service reads (not secret). The project and Web API key are the same ones as in .env.
#   create configmap      make a ConfigMap (settings) object
#   -n macroscope         in our namespace
#   --from-literal=K=V    one setting
#   `                     (backtick at the end of a line) the command carries on on the next line
kubectl create configmap macroscope-config -n macroscope `
  --from-literal=GOOGLE_PROJECT_ID=<your-project-id> `
  --from-literal=GOOGLE_API_KEY=$KEY `
  --from-literal=LOG_LEVEL=INFO

# (To change a setting later: run the same command with --dry-run=client -o yaml | kubectl apply -f -
#  on the end, then restart the services so they read it: kubectl rollout restart deployment -n macroscope)

# Secrets: a new random JWT secret and database passwords, just for the cluster
#   function New-Password { ... }  a small helper that makes one random password
#   python -c ...                  prints random hex characters (32 for a password, 64 for the JWT secret)
#   create secret generic          make a Secret object (Kubernetes keeps it out of normal views)
function New-Password { python -c "import secrets; print(secrets.token_hex(16))" }
kubectl create secret generic macroscope-secrets -n macroscope `
  --from-literal=jwt-secret=$(python -c "import secrets; print(secrets.token_hex(32))") `
  --from-literal=meal-db-password=$(New-Password) `
  --from-literal=nutrient-db-password=$(New-Password) `
  --from-literal=gap-db-password=$(New-Password) `
  --from-literal=recommender-db-password=$(New-Password)

# Each database's init.sql (the tables), so Postgres can run it the first time it starts
#   create configmap <name>      make a ConfigMap
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
data, the demo users' meals and your own. With Docker Compose running locally, **run this step from
the project folder**:

```powershell
# For each database: dump it from the local container, copy the file into the cluster's database
# pod, and load it there.
#   docker compose -f <file>  use the project's compose file (we'll be in another folder)
#   exec -T <container>       run a command in that local container (-T: no interactive terminal)
#   pg_dump -Fc -f <file>     dump the database to a file, in Postgres's own compressed format
#   compose cp                copy the dump file out of the container
#   kubectl cp                copy a file into a pod
#   kubectl exec -- <cmd>     run a command inside the pod
#   pg_restore --clean        drop the empty tables init.sql made, and load the dumped ones
#   --if-exists               don't complain about anything that isn't there
#   --no-owner                make everything belong to the cluster's database user

# The 4 databases: (container or pod name, user, database)
$dbs = @(("meal-db", "meal", "meal_db"), ("nutrient-db", "nutrient", "nutrient_db"),
         ("gap-db", "gap", "gap_db"), ("recommender-db", "recommender", "recommender_db"))

# Remember the project folder (where docker-compose.yml is), before moving away from it
$PROJ = (Get-Location).Path

# Work in the Temp folder. kubectl cp on Windows reads the "C:" in a full path as a pod name,
# so the files have to be named without a drive letter.
#   Push-Location / Pop-Location  go to a folder, and later come back to where you were
Push-Location $env:TEMP
foreach ($d in $dbs) {
    $pod, $user, $db = $d
    docker compose -f "$PROJ/docker-compose.yml" exec -T $pod pg_dump -U $user -Fc $db -f /tmp/$db.dump
    docker compose -f "$PROJ/docker-compose.yml" cp "${pod}:/tmp/$db.dump" "$db.dump"
    kubectl cp "$db.dump" "macroscope/${pod}-0:/tmp/$db.dump"
    kubectl exec -n macroscope "${pod}-0" -- pg_restore -U $user -d $db --clean --if-exists --no-owner /tmp/$db.dump
}
Pop-Location

# Check: this should say 864594, the same as locally
#   psql -c "<sql>"  run one SQL query and print the answer
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
#   describe <kind> <name>  show an object's details and status
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
#   scale deployment <name>  change how many copies (pods) of a service run
#   --replicas=4             how many
kubectl scale deployment nutrient-calc -n macroscope --replicas=4

# Load test against the cloud, and watch the autoscaler add pods in another window
#   run --rm loadtest   run the load test container once, then delete it
#   -e GATEWAY_URL=...  send the load test to the cloud site instead of the local gateway
#   --users / --seconds how many simulated people, and for how long
#   get hpa --watch     show the autoscalers, and keep updating as they change
docker compose run --rm -e GATEWAY_URL=https://$DOMAIN loadtest --users 40 --seconds 120
kubectl get hpa -n macroscope --watch

# Pod failure: delete a pod. Kubernetes starts a new one, and the other copy keeps serving.
#   delete pod -l app=meal-logging  delete the meal-logging pods (-l picks pods by their label)
#   --wait=false                    don't wait for them to finish stopping
#   get pods ... -w                 watch the replacements start
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
#   set image deployment/<name> <container>=<image>  switch the service to that image
#   rollout status                                   wait and show progress until it's done
docker build --build-arg APP_VERSION=1.1.0 -t "$REG/nutrient-calc:1.1.0" services/nutrient-calc
docker push "$REG/nutrient-calc:1.1.0"
kubectl set image deployment/nutrient-calc -n macroscope nutrient-calc="$REG/nutrient-calc:1.1.0"
kubectl rollout status deployment/nutrient-calc -n macroscope

# Rollback: go back to the version before
#   rollout undo     switch back to the previous version
#   rollout history  list the versions Kubernetes remembers
kubectl rollout undo deployment/nutrient-calc -n macroscope
kubectl rollout history deployment/nutrient-calc -n macroscope
```

## Pausing it (to save credits)

```powershell
# Turn the 2 VMs off. The databases' disks, the IP address and the load balancer stay (a small
# daily cost), so everything comes back as it was.
#   resize --num-nodes 0  run no VMs
#   --node-pool app-pool  the group of VMs to resize (our cluster's only one)
#   --zone                where the cluster is
gcloud container clusters resize macroscope --node-pool app-pool --zone australia-southeast1-a --num-nodes 0

# Turn them back on (pods start again within a few minutes)
gcloud container clusters resize macroscope --node-pool app-pool --zone australia-southeast1-a --num-nodes 2
```

**Before marking:** if the nodes are scaled to 0, scale back to 2 **at least a day before marking**,
because recovery takes several minutes and is worth checking calmly. Then confirm:

```powershell
# Every pod is "Running" and "1/1" ready
kubectl get pods -n macroscope

# The Ingress has its IP address (the $IP from step 4)
kubectl get ingress -n macroscope

# The managed certificate says "Active"
#   -o custom-columns=...  show just the name and the certificate's status
kubectl get managedcertificate -n macroscope -o custom-columns=NAME:.metadata.name,STATUS:.status.certificateStatus

# The site answers (200 means it loaded)
#   -s -o NUL -w "%{http_code}"  print only the HTTP status code
curl.exe -s -o NUL -w "%{http_code}" https://<your-domain>/
```

## Deleting it all

> **Warning: don't run this section until the assignment has been marked.** The app must be live on
> GKE during the Week 13 marking session. Deleting the cluster or the IP address can't be undone:
> rebuilding means a new IP, a new nip.io address and certificate, and loading the data again.

```powershell
# The cluster, its VMs and load balancer
#   clusters delete <name>  delete the cluster (it asks you to confirm)
gcloud container clusters delete macroscope --zone australia-southeast1-a

# The IP address and the images
#   addresses delete <name> --global       release the reserved IP address
#   repositories delete <name> --location  delete the image registry and every image in it
gcloud compute addresses delete macroscope-ip --global
gcloud artifacts repositories delete macroscope --location=australia-southeast1

# Check no database disks were left behind (delete any listed with gcloud compute disks delete)
gcloud compute disks list
```
