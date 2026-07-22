import json
d=json.load(open(r"C:\Users\Hamza Sait\Electoral\decode-politics\san-antonio-finance-data-jones-scrub\jones_research\jonesbatch_32_results.json",encoding="utf-8"))
print("Count:",len(d))
print("all3run:",all(all(x["searches_run"].values()) for x in d))
print("affil_donors:",sum(1 for x in d if x["affiliations"]))
