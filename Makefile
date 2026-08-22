.PHONY: install bronze silver gold test all dashboard clean

install:
	pip install -r requirements.txt

bronze:
	python src/ingestion/fetch_bronze.py

silver:
	python -m src.pipeline.run_silver

gold:
	python -m src.modeling.build_gold

package:
	python -m src.pipeline.build_publish

test:
	python -m pytest tests -q

all: bronze silver gold test

dashboard:
	streamlit run src/visualization/app.py

clean:
	find . -name __pycache__ -type d -exec rm -rf {} +
