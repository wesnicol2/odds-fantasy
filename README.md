# Fantasy Odds App

## Overview
This project fetches player betting lines, converts them into projected fantasy points, and prints comparisons for quick decision-making.

## Configuration
The application relies on the following environment variables (populate them in your `.env` file or configure them directly in Docker/Unraid):
- `API_KEY`
- `YAHOO_CLIENT_ID`
- `YAHOO_CLIENT_SECRET`
- `YAHOO_REDIRECT_URI`
- `YAHOO_LEAGUE_ID`

Only supply values you are comfortable sharing with the container. When running under Docker, pass them as environment variables or mount a file via `env_file`.

## Docker Workflow
1. Copy your `.env` file into the project root (or ensure the required variables are defined elsewhere).
2. Build the container image:
   ```bash
   docker build -t odds-fantasy .
   ```
3. Run the container, mounting the `data` folder so cached responses survive restarts:
   ```bash
   docker run --rm \
     --name odds-fantasy \
     --env-file .env \
     -v $(pwd)/data:/app/data \
     odds-fantasy
   ```

### Docker Compose
You can use the provided `docker-compose.yml` to simplify local and Unraid deployments:
```bash
docker compose up --build
```
Override the command or environment variables in the compose file if you need to call different entry points.

### Deploying on Unraid
1. Copy the repo (or your packaged image) onto the server.
2. From the Unraid Docker tab, add a new container and point it at the built image (`odds-fantasy:latest`) or the repository if you publish it elsewhere.
3. Under the container configuration:
   - Map `/app/data` to a persistent host path (for example `/mnt/user/appdata/odds-fantasy`).
   - Add the environment variables listed above (Unraid exposes dedicated fields for them).
   - If you want a non-default main invocation, edit the command to match.
4. Apply/Start the container. Logs will show the script output.

## Project Structure
- `main.py`: Entry point for printing the defense opportunities table.
- `config.py`: Loads environment configuration and defines shared constants.
- `odds_api.py`, `sleeper_api.py`, `predicted_stats.py`: Data sources and transformation logic.
- `data/`: Cached API responses (persist this directory across runs).
- `tests/`: Unit tests.
- `ui/`, `refactored/`: Experimental work you can ignore for container runtime.
