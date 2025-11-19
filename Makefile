install:
	pip install -e .

run_agent:
	python -m agent

run_library:
	python -m library

run_server:
	python -m server

run_client:
	python src/server/test/client.py

run_gesture:
	python -m gesture
