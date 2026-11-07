python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
make -C targets
python harness/run_campaign.py experiments/configs/main.yaml
python harness/aggregate.py results/ && python harness/plots.py results/