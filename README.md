# Certificate Claim App

This app provides one public certificate page. A participant enters a name and downloads the PDF certificate immediately.

## What it does

- Gives you one public certificate page to share with everyone
- Shows a certificate page where the participant enters a name
- Generates the PDF using your uploaded certificate template
- Downloads the PDF immediately

## Run locally

```powershell
cd C:\Users\ASUS\Documents\Apps\oracle\certificate-claim-app
python app.py
```

Then open:

```text
http://127.0.0.1:5050
```

Public claim page:

```text
http://127.0.0.1:5050
```

## Main folders

- `static/certificate-template.png`: your certificate template
- `static/fonts/NotoSans-Regular.ttf`: bundled open font used by the PDF renderer so name sizing stays correct in deployment

## Optional environment variables

- `CERTIFICATE_HOST`: server host, default `127.0.0.1`
- `CERTIFICATE_PORT`: server port, default `5050`
- `PORT`: hosting platform port override, used automatically when present
- `CERTIFICATE_FONT_PATH`: override font path if you do not want the default Calibri lookup

## Notes

- The public participant URL is the base app URL.
- The app no longer needs codes, a database, or an admin dashboard.

## Deployment direction

The easiest hosted path for this app is a Python platform that supports:

- a public web service URL
- a persistent disk or volume
- environment variables

This app is already prepared for that model.
