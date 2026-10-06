.PHONY: setup test demo check
setup:
	bash scripts/setup.sh
test:
	.venv/bin/python -m unittest discover -s tests -v
demo:
	.venv/bin/python -m reels render examples/reel.json --out out/demo
check:
	.venv/bin/python -m reels check out/demo/reel.mp4
