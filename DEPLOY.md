# Putting SnackScout on the web (Oracle Cloud, free)

Oracle's "Always Free" tier includes a small Linux server that never sleeps. SnackScout runs there 24/7 at an
`https://` address, protected by a team password. Setup takes about 30–45 minutes, once.

> Oracle's free-tier rules change from time to time. Check the current terms when you sign up.

## 1. Make an Oracle Cloud account
1. Go to **oracle.com/cloud/free** and click **Start for free**.
2. Oracle asks for a credit card to check you're a real person. Always Free resources don't charge it.
3. **Home region:** pick one close to you (e.g. *US Midwest (Chicago)* or *US East (Ashburn)*). It can't be changed later.

## 2. Create the server (VM)
In the Oracle Cloud console: **☰ → Compute → Instances → Create instance**.

| Setting | Choose |
|---|---|
| Name | `snackscout` |
| Image | **Canonical Ubuntu 24.04** (click *Change image*) |
| Shape | **Ampere → VM.Standard.A1.Flex**, **2 OCPUs, 12 GB memory** (free allows up to 4 / 24) |
| Networking | *Create new virtual cloud network* and *public subnet*, with **Assign a public IPv4 address** checked |
| SSH keys | **Generate a key pair for me** → **Save private key** (keep this file safe, e.g. `C:\Users\you\.ssh\snackscout.key`) |

Click **Create**. When it's running, copy the **Public IP address** from the instance page.

*"Out of capacity" error?* Free Ampere servers are popular. Try another *Availability domain* in the Placement section, or try again later.

## 3. Open the web ports
On the instance page: click the **Subnet** link → **Security Lists** → *Default Security List* → **Add Ingress Rules**:

- Source CIDR `0.0.0.0/0`, IP Protocol **TCP**, Destination port **80**
- Add another rule the same way with destination port **443**

## 4. Connect to the server
Open **PowerShell** on your laptop. Windows needs the key file locked to just you:

```powershell
icacls "C:\Users\you\.ssh\snackscout.key" /inheritance:r /grant:r "$($env:USERNAME):R"
ssh -i "C:\Users\you\.ssh\snackscout.key" ubuntu@YOUR.PUBLIC.IP
```

Type `yes` the first time it asks about the fingerprint.

## 5. Install SnackScout (one command)
On the server, paste:

```bash
curl -fsSL https://raw.githubusercontent.com/kieran-snack/SnackScout/main/deploy/setup-oracle.sh -o setup.sh && bash setup.sh
```

It asks for your **FTC Events username and token** and lets you **choose a team password**.
When it finishes, it prints your web address, something like:

**`https://123-45-67-89.sslip.io`**

Open it on any phone or computer, enter the team password, and you're in. Share the link and password with your team.

## 6. Bring over your scouting notes (optional)
The server starts with an empty notes database. To copy your laptop's notes up, run in **PowerShell on the laptop**
(this replaces whatever notes are on the server):

```powershell
scp -i "C:\Users\you\.ssh\snackscout.key" C:\SnackScout\snackscout.db ubuntu@YOUR.PUBLIC.IP:~/SnackScout/
ssh -i "C:\Users\you\.ssh\snackscout.key" ubuntu@YOUR.PUBLIC.IP "sudo systemctl restart snackscout"
```

After that, have everyone use the website so all notes end up in one place.

## Updating
After new code is pushed to GitHub, connect to the server (step 4) and run:

```bash
bash ~/SnackScout/deploy/update.sh
```

## Troubleshooting
| Problem | Fix |
|---|---|
| Page doesn't load at all | Check step 3 (ports 80/443). On the server: `sudo systemctl status snackscout caddy` |
| See what's happening | `sudo journalctl -u snackscout -f` (Ctrl+C to stop watching) |
| Change the team password | `nano ~/SnackScout/.env`, edit `TEAM_PASSWORD=`, save, then `sudo systemctl restart snackscout` |
| Clip downloads fail with "Sign in to confirm you're not a bot" | YouTube is blocking the server. Export a `cookies.txt` from a browser logged in to a **throwaway** YouTube account (e.g. with the "Get cookies.txt LOCALLY" extension), copy it to `~/SnackScout/youtube-cookies.txt`, uncomment the `YTDLP_COOKIES=` line in `.env`, restart. Or download clips on the laptop instead. |

**Keeping it free:** Oracle may reclaim Always Free servers that sit almost completely idle for a week.
Regular use during the season normally avoids this. If yours ever gets stopped, the Oracle console lets you start it again.
