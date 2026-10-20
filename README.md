# MacroScope

MacroScope helps you find the nutrients your diet is missing. You log what you eat, and it shows
your calories, protein, carbs, fat, fibre and over 20 vitamins and minerals against targets made
for you (from your age, sex, size, activity, goal, diet, and pregnancy or breastfeeding). It spots
what you still need to hit today's targets and what you've been short on over the last 7 days,
and suggests everyday foods that would help.

> MacroScope gives estimates from food composition data. It isn't medical advice.

It's made of four small services, each in its own container with its own Postgres database, plus a
React website, all behind one entry point:

```
browser ──HTTPS──► Google load balancer (Ingress) at https://<ip>.nip.io
                     ├─ /api/meals      ─► meal-logging     ─► meal-db + redis   food search, barcodes, meals, recipes
                     ├─ /api/nutrients  ─► nutrient-calc    ─► nutrient-db       adds up nutrients, daily totals
                     ├─ /api/gaps       ─► gap-analysis     ─► gap-db            profile, targets, what you're short on
                     ├─ /api/recommend  ─► food-recommender ─► recommender-db    foods to fill the gaps
                     └─ /               ─► frontend (React, served by Nginx)
         all on Google Kubernetes Engine (GKE) in Sydney, spread across 2 identical VMs
```

It's live at **https://34-120-54-167.nip.io**. This README takes you from nothing to your own copy
of that deployment, in order (steps 1-14).

**It costs money while it runs**: about A$5-7 a day (A$150-210 a month) for the 2 VMs, the load
balancer and the disks, from your Google Cloud credits. "Pausing it" near the end turns the VMs off
between sessions.

## Where to find things

This README is the place to start, and has everything needed to deploy. The other files go deeper
into one topic each.

| If you want to... | Go to |
|---|---|
| **deploy MacroScope to Google Cloud from scratch** | this README, steps 1-14, in order |
| **bring a paused deployment back** (or pause it) | ["Pausing it"](#pausing-it-to-save-credits) in this README. Don't redo the steps. |
| check the deployment is working, and log in as a demo user | [step 14](#14-check-it-works) in this README |
| show scaling, failures, a rolling update and a rollback on GKE | ["Demo commands"](#demo-commands) in this README |
| delete the deployment | ["Deleting it all"](#deleting-it-all) in this README |
| run the app on your own computer, and see what the website does | [docs/running-locally.md](docs/running-locally.md) |
| run the tests, the load test and the failure demos locally (with their results) | [docs/testing.md](docs/testing.md) |
| see every API endpoint, and call them with `curl` | [docs/api.md](docs/api.md) |
| understand how it's designed and why: services, logins, targets, suggestions, GKE | [docs/architecture.md](docs/architecture.md) |
| know what each Kubernetes file makes | [k8s/README.md](k8s/README.md) |
| know where the food data comes from, how it's cleaned, and the row counts | [etl/README.md](etl/README.md) |
| check the nutrient targets against the official NHMRC values | [etl/REFERENCE_INTAKES.md](etl/REFERENCE_INTAKES.md) |
| see how AI was used to build it (every prompt) | [AI-log.md](AI-log.md) |

## Before you start

You need:

- **Docker Desktop**, running. It includes Docker Compose and `kubectl`. Docker builds the images,
  and runs the loader that prepares the food data before it's copied to the cloud.
- **Python 3.12 or newer**, to download the food data and make random passwords.
- **A Google Cloud project with billing turned on** (free credits are fine).
- **The Google Cloud CLI (`gcloud`)**. Install it, then close and reopen the terminal:
  - Windows: `winget install Google.CloudSDK`
  - macOS: `brew install --cask gcloud-cli` (needs [Homebrew](https://brew.sh))
  - Linux: follow https://cloud.google.com/sdk/docs/install. Without Docker Desktop, also run
    `gcloud components install kubectl`.

**Already deployed in this project, and just paused?** Don't follow the steps: steps 9-11 would
replace what's there, and step 11 would overwrite the cloud databases. Go to "Pausing it" below and
turn the VMs back on.

How to follow this guide:

- **Open a terminal in the project folder** and run every command from there.
- **Copy each grey block whole and paste it in.** Blocks marked **Windows (PowerShell)** or
  **macOS / Linux** are for that system only; unmarked blocks are the same on every system.
- **Wait for each block to finish, and check it matches "You should see"**, before going on. Each
  step needs the ones before it to have worked.
- **On macOS and Linux, Python is `python3`**; on Windows it's `python`. The blocks already use the
  right one.
- **Re-running a step after a failure is fine.** Commands that create something (a registry, the
  cluster, the IP address, a setting) say "already exists" the second time: that's not a problem,
  carry on.

## 1. Set up Google login in your project

People sign up and log in through Google Cloud Identity Platform. In the Google Cloud console
(https://console.cloud.google.com), with your project picked at the top of the page:

1. Search for **Identity Platform** and click **Enable** (free for up to 50,000 users a month).
2. Under **Providers**, click **Add a provider**, choose **Email / Password**, turn it on and save.
3. Add the **Google** provider too, for the website's **Continue with Google** button. Google fills
   in the details for you.
4. Click **Application setup details** (top right). Keep this open: you need the `apiKey` in step 2.

## 2. Make the `.env` file

Copy the template (the same command works on every system):

```bash
cp .env.example .env
```

Make a random secret for the services to sign their tokens with, and copy what it prints:

Windows (PowerShell):

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

macOS / Linux:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Open `.env` in a text editor and change these three lines. Put the value straight after the `=`,
with no spaces or quotes, then save:

| Line | What to put | Where to find it |
|---|---|---|
| `GOOGLE_PROJECT_ID=` | your project's ID, e.g. `macroscope-123456` | the project picker at the top of the Google Cloud console (the ID, not the name) |
| `GOOGLE_API_KEY=` | the Web API key, starts with `AIza` | `apiKey` in Identity Platform's **Application setup details** (step 1) |
| `JWT_SECRET=` | the 64 characters printed above | the command above |

Leave everything else as it is. The database passwords are only used on your computer, and the
cloud gets new random ones in step 9. The deployment reads the project ID and Web API key from
`.env`, so this is the only place you type them.

## 3. Prepare the food data

The cloud databases are filled by copying them from local ones (step 11), so first the whole app is
started locally with Docker Compose, and the data is loaded into it. The food data is Australian,
AUSNUT 2023 (CC BY 4.0), with USDA FoodData Central (public domain) filling in everything else,
including packaged foods with barcodes. How it's cleaned is in [etl/README.md](etl/README.md).

**3a. Start the whole app.** This builds the images, so the first time takes a few minutes. Then
wait about 30 seconds and list the containers:

```bash
docker compose up --build -d
```

```bash
docker compose ps
```

You should see 11 containers (the 4 services, their 4 databases, redis, frontend and gateway), all
"healthy". If any aren't, wait a little and run `docker compose ps` again. If one keeps
restarting, `docker compose logs <name>` shows why (most often a value in `.env`). If it says
"failed to connect to the docker API" or "Cannot connect to the Docker daemon", Docker Desktop
isn't running: open it, wait until it says it's running, and try again.

**3b. Download the food data** into `etl/data/`: the Australian data (about 6 MB, already there if
you have the project as a ZIP) and the USDA data (about 440 MB to download, 3 GB unpacked).

Windows (PowerShell):

```powershell
python etl/download_ausnut.py
python etl/download_usda.py
```

macOS / Linux:

```bash
python3 etl/download_ausnut.py
python3 etl/download_usda.py
```

**3c. Load it** into the 4 local databases (a few minutes):

```bash
docker compose run --rm etl
```

You should see a table of row counts at the end, totalling **1,030,440**.

**3d. Make the 4 demo users**, with 3 weeks of meals each (about a minute). The command passes in
today's date, because the container's clock is on UTC.

Windows (PowerShell):

```powershell
docker compose run --rm -e TODAY=$(Get-Date -Format yyyy-MM-dd) --entrypoint python etl seed_demo_users.py
```

macOS / Linux:

```bash
docker compose run --rm -e TODAY=$(date +%F) --entrypoint python etl seed_demo_users.py
```

You should see one line per demo user (alex, priya, sam, jess), then "Done". If it fails with
"Name or service not known", the app from 3a isn't running. If it fails with `KeyError` or a 500
error, the data from 3c isn't loaded.

**Keep the local app running** until step 11, which copies its databases. (It's also usable at
http://localhost:8080; [docs/running-locally.md](docs/running-locally.md) covers that.)

## 4. Set the variables the deployment commands use

The commands from here on use a few values: your project ID and Web API key (read from `.env`), and
the address of your image registry. This block puts them in variables. Variables only last as long
as the terminal window, so **if you open a new terminal, run this block again** (and from step 8 on,
step 8's first block too).

Windows (PowerShell):

```powershell
$PROJECT = ((Get-Content .env) | Where-Object { $_ -match '^GOOGLE_PROJECT_ID=' }) -replace '^GOOGLE_PROJECT_ID=', ''
$KEY = ((Get-Content .env) | Where-Object { $_ -match '^GOOGLE_API_KEY=' }) -replace '^GOOGLE_API_KEY=', ''
$REG = "australia-southeast1-docker.pkg.dev/$PROJECT/macroscope"
"project: $PROJECT"
"key: $KEY"
```

macOS / Linux:

```bash
PROJECT=$(grep '^GOOGLE_PROJECT_ID=' .env | cut -d= -f2- | tr -d '\r')
KEY=$(grep '^GOOGLE_API_KEY=' .env | cut -d= -f2- | tr -d '\r')
REG="australia-southeast1-docker.pkg.dev/$PROJECT/macroscope"
echo "project: $PROJECT"
echo "key: $KEY"
```

You should see your project ID and your Web API key. If either is empty, check the line in `.env`.

## 5. Log in to Google Cloud and turn on its services

This logs you in (it opens a browser), makes your project the default for every `gcloud` command,
adds the plugin `kubectl` needs to log in to GKE, and turns on Kubernetes Engine, Artifact Registry
(where the images are stored) and Compute Engine (VMs, disks, IPs). The last command takes a minute.

```bash
gcloud auth login
gcloud config set project $PROJECT
gcloud components install gke-gcloud-auth-plugin
gcloud services enable container.googleapis.com artifactregistry.googleapis.com compute.googleapis.com
```

If `gcloud components install` says the component manager is disabled, you installed gcloud with
`apt` or `dnf`. Install the plugin that way instead:
`sudo apt-get install google-cloud-cli-gke-gcloud-auth-plugin` (or the same with `dnf`).

## 6. Build the images and upload them

Make the image registry in Sydney, and let Docker log in to it with your gcloud login:

```bash
gcloud artifacts repositories create macroscope --repository-format=docker --location=australia-southeast1
gcloud auth configure-docker australia-southeast1-docker.pkg.dev --quiet
```

Then the next block:

- points the image names in `k8s/30-services.yaml` and `k8s/40-frontend.yaml` at your registry
  (replacing whatever registry is there now)
- builds each service with its version baked in (shown at `/version` and in the website footer),
  and uploads it. The versions must match the image tags in those two files.
- builds and uploads the website the same way

`--platform linux/amd64` builds for the cluster's VMs, which are Intel/AMD. It matters on Apple
Silicon Macs, where an image built for ARM wouldn't start on them. This takes several minutes.

Windows (PowerShell):

```powershell
foreach ($f in "k8s/30-services.yaml", "k8s/40-frontend.yaml") {
    [IO.File]::WriteAllText("$PWD/$f", ((Get-Content $f -Raw) -replace 'image: \S+/macroscope/', "image: $REG/"))
}
$versions = @{ "meal-logging" = "1.0.1"; "nutrient-calc" = "1.0.0"; "gap-analysis" = "1.0.1"; "food-recommender" = "1.0.2" }
foreach ($s in $versions.Keys) {
    $v = $versions[$s]
    docker build --platform linux/amd64 --build-arg APP_VERSION=$v -t "$REG/${s}:$v" "services/$s"
    docker push "$REG/${s}:$v"
}
docker build --platform linux/amd64 -t "$REG/frontend:1.0.6" frontend
docker push "$REG/frontend:1.0.6"
```

macOS / Linux:

```bash
perl -pi -e "s#image: \S+/macroscope/#image: $REG/#" k8s/30-services.yaml k8s/40-frontend.yaml
for sv in meal-logging:1.0.1 nutrient-calc:1.0.0 gap-analysis:1.0.1 food-recommender:1.0.2; do
    s=${sv%%:*}; v=${sv#*:}
    docker build --platform linux/amd64 --build-arg APP_VERSION=${v} -t "${REG}/${s}:${v}" "services/${s}"
    docker push "${REG}/${s}:${v}"
done
docker build --platform linux/amd64 -t "$REG/frontend:1.0.6" frontend
docker push "$REG/frontend:1.0.6"
```

Check all 5 images arrived:

```bash
gcloud artifacts docker images list $REG --include-tags --filter="tags:*" --format="table(package.basename(),tags)"
```

You should see these 5 rows (and older versions too, if you've deployed before): meal-logging
1.0.1, nutrient-calc 1.0.0, gap-analysis 1.0.1, food-recommender 1.0.2 and frontend 1.0.6.

## 7. Make the cluster (the 2 VMs)

This makes a GKE cluster in one zone in Sydney (a zonal cluster's management fee is covered by
Google's free tier) with 2 identical `e2-standard-2` VMs (2 vCPUs and 8 GB of memory each, with a
30 GB boot disk), and points `kubectl` at it. It takes about 5 minutes.

```bash
gcloud container clusters create macroscope --zone australia-southeast1-a --num-nodes 2 --machine-type e2-standard-2 --disk-size 30
gcloud container clusters get-credentials macroscope --zone australia-southeast1-a
kubectl get nodes
```

You should see 2 nodes, both "Ready". If the first command says the cluster "already exists" and
the last says "No resources found", the cluster is there but paused (0 VMs): turn it back on as in
"Pausing it" below.

The VMs are in a node pool called `default-pool`. (The live deployment's pool is called `app-pool`,
made later with `gcloud container node-pools create`.)

## 8. Reserve the IP address and fill in the domain

Reserve a fixed public IP address for the load balancer (only once):

```bash
gcloud compute addresses create macroscope-ip --global
```

The web address is that IP with dashes, plus `.nip.io` (34.120.5.6 becomes `34-120-5-6.nip.io`), so
no domain needs buying. This block gets the IP and makes the domain. **Run it again in any new
terminal**, after step 4's block:

Windows (PowerShell):

```powershell
$IP = gcloud compute addresses describe macroscope-ip --global --format="value(address)"
$DOMAIN = ($IP -replace '\.', '-') + ".nip.io"
"domain: $DOMAIN"
```

macOS / Linux:

```bash
IP=$(gcloud compute addresses describe macroscope-ip --global --format="value(address)")
DOMAIN="${IP//./-}.nip.io"
echo "domain: $DOMAIN"
```

You should see your domain, like `34-120-5-6.nip.io`. Now put it into the HTTPS certificate in
`k8s/60-ingress.yaml` (only once):

Windows (PowerShell):

```powershell
$file = "$PWD/k8s/60-ingress.yaml"
[IO.File]::WriteAllText($file, ((Get-Content $file -Raw) -replace '- [0-9-]+\.nip\.io', "- $DOMAIN"))
```

macOS / Linux:

```bash
perl -pi -e "s/- [0-9-]+\.nip\.io/- $DOMAIN/" k8s/60-ingress.yaml
```

## 9. Settings and secrets

These aren't in the `k8s/` files, so no passwords end up in git. First the namespace everything
lives in, and each database's `init.sql` (its tables), which Postgres runs the first time it starts:

```bash
kubectl apply -f k8s/00-namespace.yaml
kubectl create configmap meal-db-init -n macroscope --from-file=init.sql=services/meal-logging/db/init.sql
kubectl create configmap nutrient-db-init -n macroscope --from-file=init.sql=services/nutrient-calc/db/init.sql
kubectl create configmap gap-db-init -n macroscope --from-file=init.sql=services/gap-analysis/db/init.sql
kubectl create configmap recommender-db-init -n macroscope --from-file=init.sql=services/food-recommender/db/init.sql
```

Then the settings every service reads (the project and Web API key from `.env`), and the secrets:
a new random JWT secret and database passwords, just for the cluster.

Windows (PowerShell):

```powershell
kubectl create configmap macroscope-config -n macroscope --from-literal=GOOGLE_PROJECT_ID=$PROJECT --from-literal=GOOGLE_API_KEY=$KEY --from-literal=LOG_LEVEL=INFO
function New-Password { python -c "import secrets; print(secrets.token_hex(16))" }
kubectl create secret generic macroscope-secrets -n macroscope `
  --from-literal=jwt-secret=$(python -c "import secrets; print(secrets.token_hex(32))") `
  --from-literal=meal-db-password=$(New-Password) `
  --from-literal=nutrient-db-password=$(New-Password) `
  --from-literal=gap-db-password=$(New-Password) `
  --from-literal=recommender-db-password=$(New-Password)
```

macOS / Linux:

```bash
kubectl create configmap macroscope-config -n macroscope --from-literal=GOOGLE_PROJECT_ID=$PROJECT --from-literal=GOOGLE_API_KEY=$KEY --from-literal=LOG_LEVEL=INFO
new_password() { python3 -c "import secrets; print(secrets.token_hex(16))"; }
kubectl create secret generic macroscope-secrets -n macroscope \
  --from-literal=jwt-secret=$(python3 -c "import secrets; print(secrets.token_hex(32))") \
  --from-literal=meal-db-password=$(new_password) \
  --from-literal=nutrient-db-password=$(new_password) \
  --from-literal=gap-db-password=$(new_password) \
  --from-literal=recommender-db-password=$(new_password)
```

You should see `namespace/macroscope created`, then a `created` line for each of the 5 configmaps
and the secret. (If one says "already exists", it's from an earlier try and can stay. To change a
setting later, add `--dry-run=client -o yaml | kubectl apply -f -` to the end of its command, then
run `kubectl rollout restart deployment -n macroscope` so the services read it.)

## 10. Start everything

This creates everything in the `k8s/` folder (what each file makes is listed in
[k8s/README.md](k8s/README.md)), then watches the pods start. Press Ctrl+C to stop watching.

```bash
kubectl apply -f k8s/
kubectl get pods -n macroscope -w
```

You should see, after a minute or two, every pod "Running" and "1/1" ready. The load balancer
takes another 5-10 minutes to appear: `kubectl get ingress -n macroscope` shows its IP once it's
ready.

## 11. Copy the food data and demo users into the cloud databases

With the local app from step 3 still running, this dumps each local database, copies the file into
the matching database pod in the cluster, and loads it there (replacing the empty tables). On
Windows it works in the Temp folder, because `kubectl cp` reads the `C:` in a full path as a pod
name.

Windows (PowerShell):

```powershell
$dbs = @(("meal-db", "meal", "meal_db"), ("nutrient-db", "nutrient", "nutrient_db"), ("gap-db", "gap", "gap_db"), ("recommender-db", "recommender", "recommender_db"))
$PROJ = (Get-Location).Path
Push-Location $env:TEMP
foreach ($d in $dbs) {
    $pod, $user, $db = $d
    docker compose -f "$PROJ/docker-compose.yml" exec -T $pod pg_dump -U $user -Fc $db -f /tmp/$db.dump
    docker compose -f "$PROJ/docker-compose.yml" cp "${pod}:/tmp/$db.dump" "$db.dump"
    kubectl cp "$db.dump" "macroscope/${pod}-0:/tmp/$db.dump"
    kubectl exec -n macroscope "${pod}-0" -- pg_restore -U $user -d $db --clean --if-exists --no-owner /tmp/$db.dump
}
Pop-Location
```

macOS / Linux:

```bash
TMP=$(mktemp -d)
for d in "meal-db meal meal_db" "nutrient-db nutrient nutrient_db" "gap-db gap gap_db" "recommender-db recommender recommender_db"; do
    read pod user db <<< "$d"
    docker compose exec -T ${pod} pg_dump -U ${user} -Fc ${db} -f /tmp/${db}.dump
    docker compose cp "${pod}:/tmp/${db}.dump" "${TMP}/${db}.dump"
    kubectl cp "${TMP}/${db}.dump" "macroscope/${pod}-0:/tmp/${db}.dump"
    kubectl exec -n macroscope "${pod}-0" -- pg_restore -U ${user} -d ${db} --clean --if-exists --no-owner /tmp/${db}.dump
done
```

Check the data arrived:

```bash
kubectl exec -n macroscope nutrient-db-0 -- psql -U nutrient -d nutrient_db -c "SELECT count(*) FROM food_nutrient"
```

You should see **864594**, the same as locally. You can stop the local app now with
`docker compose down` (its data is kept).

## 12. Allow logins from the new address

In the Google Cloud console, under **Identity Platform > Settings > Security > Authorized domains**,
click **Add domain** and add your domain from step 8. Google only lets people log in from listed
sites.

## 13. Turn on HTTPS only

Google issues the certificate once the load balancer is up and the domain points at it, which
takes 15-60 minutes. Until then, the site works at `http://<your domain>`. Check the certificate:

```bash
kubectl describe managedcertificate macroscope-cert -n macroscope
```

When "Certificate Status" says **Active**, send http:// visitors to https:// (the redirect is
defined in `60-ingress.yaml`):

```bash
kubectl annotate ingress macroscope -n macroscope networking.gke.io/v1beta1.FrontendConfig=macroscope-https-redirect
```

## 14. Check it works

```bash
kubectl get pods -n macroscope -o wide
kubectl get ingress -n macroscope
kubectl get managedcertificate -n macroscope -o custom-columns=NAME:.metadata.name,STATUS:.status.certificateStatus
```

You should see every pod "Running" and "1/1", spread across both nodes (the NODE column); the
Ingress with your IP address; and the certificate "Active". Then ask the site and a service
(`curl.exe` on Windows, because plain `curl` in Windows PowerShell is a different command):

Windows (PowerShell):

```powershell
curl.exe -s -o NUL -w "%{http_code}`n" https://$DOMAIN/
curl.exe https://$DOMAIN/api/nutrients/version
```

macOS / Linux:

```bash
curl -s -o /dev/null -w "%{http_code}\n" "https://$DOMAIN/"
curl "https://$DOMAIN/api/nutrients/version"
```

You should see `200`, then the service's version and which pod answered.

Open **https://&lt;your domain&gt;** in a browser. Make an account, or log in as a demo user.
They all have the password **`MacroScope-demo-2026`**:

| Email | Who they are | What the app finds |
|---|---|---|
| `alex@macroscope-demo.test` | 29, office job, lots of white bread, rice and chicken | short on magnesium, fibre, vitamin C and more |
| `priya@macroscope-demo.test` | 25, vegetarian, no legumes or fortified cereal | very short on iron (vegetarians need 1.8 times as much) |
| `sam@macroscope-demo.test` | 35, trying to lose weight, no fish, eggs or mushrooms | short on vitamin D, iron and calcium |
| `jess@macroscope-demo.test` | 32, 22 weeks pregnant, eats well | short on iron (27 mg a day in pregnancy) |

Each service also has a page where you can try out its API, e.g. `https://<your domain>/api/nutrients/docs`
(swap `nutrients` for `meals`, `gaps` or `recommend`).

## Demo commands

Same on every system, with the step 4 and step 8 variables set in this terminal. Run each block on
its own.

**Scaling**: run 4 copies of nutrient-calc (the autoscaler can also do this by itself):

```bash
kubectl scale deployment nutrient-calc -n macroscope --replicas=4
```

**Autoscaling under load**: run the load test against the cloud (40 simulated people for 2
minutes), and in a second terminal watch the autoscalers add pods:

```bash
docker compose run --rm -e GATEWAY_URL=https://$DOMAIN loadtest --users 40 --seconds 120
```

```bash
kubectl get hpa -n macroscope --watch
```

**Pod failure**: delete the meal-logging pods, and watch Kubernetes start new ones straight away
while the site keeps working (Ctrl+C to stop watching):

```bash
kubectl delete pod -n macroscope -l app=meal-logging --wait=false
kubectl get pods -n macroscope -l app=meal-logging -w
```

**VM failure**: every service has a pod on each VM, so losing one doesn't take anything down.
"Draining" a VM pretends it has failed: everything moves to the other VM, and the databases move
with their disks (about a minute). List the nodes, and copy one name in place of `NODE-NAME` below:

```bash
kubectl get nodes
```

```bash
kubectl drain NODE-NAME --ignore-daemonsets --delete-emptydir-data
kubectl get pods -n macroscope -o wide
```

Bring the VM back into use:

```bash
kubectl uncordon NODE-NAME
```

**Rolling update**: build and push version 1.1.0 of nutrient-calc, then switch to it. Pods are
replaced one at a time, and the website footer shows the new version:

```bash
docker build --platform linux/amd64 --build-arg APP_VERSION=1.1.0 -t "$REG/nutrient-calc:1.1.0" services/nutrient-calc
docker push "$REG/nutrient-calc:1.1.0"
kubectl set image deployment/nutrient-calc -n macroscope nutrient-calc="$REG/nutrient-calc:1.1.0"
kubectl rollout status deployment/nutrient-calc -n macroscope
```

**Rollback**: go back to the version before:

```bash
kubectl rollout undo deployment/nutrient-calc -n macroscope
kubectl rollout history deployment/nutrient-calc -n macroscope
```

More demos, with results, are in [docs/testing.md](docs/testing.md).

## Pausing it (to save credits)

Turning the 2 VMs off stops most of the cost. The disks, the IP address and the load balancer stay
(a small daily cost), so everything comes back as it was. These commands look up the node pool's
name themselves (`default-pool` if you followed step 7, `app-pool` on the live deployment), so they
work on their own in any terminal, on every system.

Turn the VMs off:

```bash
gcloud container clusters resize macroscope --node-pool $(gcloud container node-pools list --cluster macroscope --zone australia-southeast1-a --format="value(name)") --zone australia-southeast1-a --num-nodes 0 --quiet
```

Turn them back on:

```bash
gcloud container clusters resize macroscope --node-pool $(gcloud container node-pools list --cluster macroscope --zone australia-southeast1-a --format="value(name)") --zone australia-southeast1-a --num-nodes 2 --quiet
```

The pods start again within a few minutes. Then check with step 14 (run step 8's first block in
the terminal first, so `$DOMAIN` is set).

## Deleting it all

Deleting can't be undone. Unlike pausing, it removes the data and the IP address, so bringing the
app back means going through steps 6-14 again, with a new nip.io address and certificate.

This deletes the cluster (with its VMs and load balancer), the IP address, and the image registry
with every image in it. Each asks you to confirm. The last command lists any disks left behind;
delete those with `gcloud compute disks delete <name> --zone australia-southeast1-a`.

```bash
gcloud container clusters delete macroscope --zone australia-southeast1-a
gcloud compute addresses delete macroscope-ip --global
gcloud artifacts repositories delete macroscope --location=australia-southeast1
gcloud compute disks list
```

## What's in each folder

```
README.md            start here: what MacroScope is, and deploying it to Google Cloud
AI-log.md            how AI was used to build it, prompt by prompt
docker-compose.yml   runs the whole app on your computer (and the data loader)
.env.example         the template for .env, your settings (step 2)
gateway/nginx.conf   the local gateway: /api/... to the right service, everything else to the website
frontend/            the React website, and the Nginx that serves it
services/<name>/     one folder per service: code (app/), tests, database setup (db/init.sql)
etl/                 downloads and loads the food data; seed_demo_users.py makes the demo users
  README.md            the food data: sources, cleaning, row counts
  REFERENCE_INTAKES.md the nutrient targets, checked against the NHMRC tables
loadtest/            the load test
k8s/                 the Kubernetes files for GKE
  README.md            what each file makes
docs/
  running-locally.md   running and using the app on your own computer
  testing.md           tests, the load test and failure demos, with results
  api.md               every API endpoint
  architecture.md      how it's designed and why
```
