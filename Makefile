install:
	pip install -r requirements.txt

run:
	python main.py --url "https://example.com" --task "Analyze landing for conversion improvements"

dev-run:
	python main.py --url "https://example.com" --task "Analyze landing" --output output/dev.json

lint:
	echo "No linter configured"

test:
	python -m unittest discover -s tests -p "test_*.py" -v

clean:
	rm -rf __pycache__ output/*.json
