test:
	black --check nacl
	flake8 nacl
	pytest --doctest-modules
