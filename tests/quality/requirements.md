# Folder
All new quality tests should be stored under a `tests/quality/results/[YYYY-MM-DD_HH:MM]` new folder, timestamp coming from the time the `python3 -m src.cli quality-test` strated.

# Files
There should be files created in the designated folder.
- `prompt.md` - the current LLM prompt saved to a file
- `report.md` - overall report for the whole quality test
- `report_[test_case].md` - report for a single test IF multiple tests are ran for multiple models
- `output_[test_case]_[model_name]_[#run].md` - question and LLM response 

# Modes
Running quality test can be done:
- for a single run or multiple runs via the `--runs [N]` parameter
- for all the test cases or a single test case via the `--test [test-case]` parameter
- for a single model via the `--model [model-name]` parameter or all the models via the `--all-models` parameter (without any such parameter in runs on the single default model)

# Reporting in detail

## Result indicator emoji
✅: passed, passed with maximum score
⚠️: failed 
❌: failed, failed with less than half achievable score
💀: LLM (timeout, recitation error, etc.) or LLM judge malfunction

## Overall report
- Total time: [x]m [y.zw]s
- Total cost: $[x.yzvw]
- Total queries: [x]
- Best score: [xy.z]% - [model-name] (maximum of sum of scores / possible max score, averaged on multiple runs, ONLY present for multiple models or for multiple runs)
- Test cases: [x], [y], ...

Table with columns:
- model name
- average score % (with standard deviation for multiple runs or multiple tests)
- average time per query % (with standard deviation for multiple runs or multiple tests)
- average cost per query % (with standard deviation for multiple runs or multiple tests)

## Summary per model

## Individual test result
- ### test case name
- **query**
- **model name**
- score: [emoji] [achieved score] / [maximum score] [score percentage]
- tokens
- cost
- output character count
- #### Requirements
    - [emoji] **[check title]** *[type]* ([achieved score]/[maximum score]): [description]
        - *[outcome]*
- `output` file linked

## Test case report

## Reporting on different modes
### single run, single test case, single model
- `report.md`
    - "Overall report"
    - "Individual test result"
- `output_[test_case]_[model_name].md` referred in `report.md`
- No visualization needed

### multiple run, single test case, single model
- `report.md`
    - "Overall report"
    - "Individual test result" for each run
- `output_[test_case]_[model_name]_[#run].md` referred in `report.md`
- No visualization needed

### single run, multiple test cases, single model
- `report.md`
    - "Overall report" + total score
    - "Individual test result" for each test case
- `output_[test_case]_[model_name].md` referred in `report.md`
- No visualization needed

### single run, single test case, multiple models
- `report.md`
    - "Overall report"
    - "Individual test result" for each model
- `output_[test_case]_[model_name].md` referred in `report.md`
- Visualisation: `chart.png` 

### single run, multiple test cases, multiple models
- `report.md`
    - "Overall report" with summary table comparing models across all tests.
    - "Summary per model" section detailing each model's performance across all test cases.
- `report_[test_case].md` for each test case, referred in `report.md`
    - A summary for that test case.
    - A comparison table for models on this test case.
    - "Individual test result" for each model for this test case.
- Visualization: `chart.png` comparing models' overall average performance, referred in `report.md`

### multiple runs, multiple test cases, single model
- `report.md`
    - "Overall report" with averaged results and standard deviation.
    - "Summary per test case": For each test case, show the average score, time, cost over the N runs.
- `report_[test_case].md` for each test case, referred in `report.md`
    - Summary for the test case across all runs (average score, overall time, overall cost, and std. dev.).
    - "Individual test result" for each run of this test case.
- `output_[test_case]_[model_name]_[#run].md` for each run of each test case, `report_[test_case].md`
- Visualization not needed

### multiple runs, single test case, multiple models
- `report.md`
    - "Overall report" with summary table comparing models (results averaged over runs).
    - "Summary per model" section detailing each model's performance, including averages and standard deviations.
- `report_[test_case]_[model_name].md`, referred in `report.md`
    - Summary for the model (averaged results).
    - List of its "Individual test results" for each run.
- `output_[test_case]_[model_name]_[#run].md` for each run of each model, referred in `report_[test_case]_[model_name].md`
- Visualization: `chart.png` comparing models' average performance with error bars for standard deviation.

### multiple runs, multiple test cases, multiple models
- `report.md`
    - "Overall report" with summary table comparing models (results averaged over all tests and runs).
    - "Summary per model" section detailing each model's average performance across all tests and runs.
- `report_[test_case].md` for each test case, referred in `report.md`
    - Summary for the test case, comparing models (averaged over runs).
- `report_[test_case]_[model_name].md` for each test case and model combination, referred in `report_[test_case].md`
    - For each model, a list of its "Individual test results" for each run on this test case.
- `output_[test_case]_[model_name]_[#run].md` for each combination, referred in `report_[test_case]_[model_name].md`
- Visualization: `chart.png` comparing models' overall average performance with error bars for standard deviation, referred in `report.md`
- Visualization: `chart_[test_case].png` comparing models for a certain test case, overall average performance with error bars for starndard deviation, referred in `report_[test_case].md`