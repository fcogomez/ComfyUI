import os
import json
import glob
import requests
from flask import Flask, jsonify, request, render_template, render_template_string, send_file
from flask_bootstrap import Bootstrap
from os import mkdir
from os.path import isfile, isdir
import uuid

if "BASE_URL" not in os.environ:
    # If 'BASE_URL' environment variable doesn't exist, we set it to localhost
    BASE_URL = "http://localhost:5000"
else:
    # Otherwise, set it to the value stored in the environment variable
    BASE_URL = os.environ["BASE_URL"]

app = Flask(__name__)
Bootstrap(app) # Added this to enable Flask-Bootstrap for better UI

WORKFLOW_DIR = '/storage/workflows'

import collections.abc

def deep_update(d, u):
    for k, v in u.items():
        if isinstance(v, collections.abc.Mapping):
            d[k] = deep_update(d.get(k, {}), v)
        else:
            d[k] = v
    return d

@app.route('/workflow/<string:workflow_name>', methods=['POST'])
def execute_and_save_parameters(workflow_name):
    workflow_file = f"{WORKFLOW_DIR}/{workflow_name}.json"
    workflow_mapping_file = f"{WORKFLOW_DIR}/{workflow_name}_mapping.json"

    if not isfile(workflow_file):
        return jsonify({'error': f"No workflow named /storage/workflows/{workflow_name}.json found."}), 404

    with open(workflow_file, "r") as f:
        workflow_data = json.load(f)

    if not isfile(workflow_file):
        return jsonify({'error': f"No workflow mapping /storage/workflows/{workflow_name}_mapping.json found."}), 404

    with open(workflow_mapping_file, "r") as f:
        workflow_mapping_data = json.load(f)

    parameters = request.get_json()

    # Replace the workflow mapping values with the inputs.

    final_mapping_data = {}
    for key in workflow_mapping_data:
        input_keys = workflow_mapping_data[key]["inputs"].keys()

        final_mapping_data[key] = {}
        final_mapping_data[key]["inputs"] = {}

        for input_key in input_keys:
            param_name = workflow_mapping_data[key]["inputs"][input_key]

            try:
                final_mapping_data[key]["inputs"][input_key] = parameters[param_name]
            except:
                print("Skipping - key not in params.")

    # Prepare a uuid for a job to track.
    job_id = str(uuid.uuid4())

    workflow_mapped = {}
    workflow_mapped = deep_update(workflow_mapped, workflow_data)

    workflow_mapped = deep_update(workflow_mapped, final_mapping_data)

    key_of_save_image_node = None

    for key in workflow_mapped.keys():
        class_type = workflow_mapped[key]["class_type"]

        if  class_type == "SaveImage" or class_type == "Save Image" or class_type == "VHS_VideoCombine":
            key_of_save_image_node = key


    workflow_mapped[key]["inputs"]["filename_prefix"] = f"job_{job_id}"

    workflow_mapped = deep_update(workflow_mapped, { key_of_save_image_node: {
        "inputs": {
            "filename_prefix": f"job_{job_id}"
        } 
    } } )

    print("---------------------")
    print(workflow_mapped)


    url = 'http://localhost:8188/prompt'
    headers = {'Content-type': 'application/json'}

    response = requests.post(url, headers=headers, data=json.dumps({"prompt": workflow_mapped}))

    print(response)
    print(response.json)
    
    return {"ok": True, "jobId": job_id}, 200

@app.route('/download/<string:filename>')
def serve_completed_job(filename):
    return send_file(f"/storage/ComfyUI/output/{filename}", mimetype='image/png')

@app.route('/status/<job_id>')
def jobs_ui(job_id):
    file_names = [f"{BASE_URL}/download/{path.split('/')[-1]}" for path in glob.glob(os.path.join("/storage/ComfyUI/output/", f"job_{job_id}*"))]

    if len(file_names) > 0:
        return {"state": "completed", "job": { "returnvalue": { "images": file_names } } }
    else:
        return {"state": "in_progress", "ok": True, "jobId": job_id}


workflows_ui_template = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Workflows UI</title>
    {% if not workflows|length %}
        <style type="text/css">
            .workflow-table {
                display: none;
            }
        </style>
    {% endif %}
    <!-- Include Flask-Bootstrap CSS -->
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" integrity="sha384-T3c6CoIi6uLrA9TneNEoa7RxnatzjcDSCmG1MXxSR1GAsXEV/Dwwykc2MPK8M2HN" crossorigin="anonymous">
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.min.js" integrity="sha384-BBtl+eGJRgqQAUMxJ7pMwbEyER4l1g+O15P+16Ep7Q9Q+zqX6gSbd85u4mG4QzX+" crossorigin="anonymous"></script>
</head>
<body>
    <div class="row justify-content-center content-wrapper mb-5 mx-3 mx-md-5 mx-xl-auto">
        <div class="col mb-5 mx-3 mx-md-5 mx-xl-auto">
            <h1>Current Workflows and Mappings Available</h1>
            {{ no_workflows_message|safe }}

            <table class="table table-striped workflows-table">
                <thead>
                    <tr>
                        <th scope="col">Workflow Name</th>
                        <th scope="col">Link</th>
                    </tr>
                </thead>
                <tbody>
                    {% for workflow in workflows %}
                    <tr>
                        <td>{{ workflow }}</td>
                        <td><a href="/workflows/{{ workflow }}">View Workflow JSON</a></td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>
"""

@app.route('/', methods=['GET'])
def workflows_ui():
    workflows = [os.path.basename(f) for f in sorted(glob.iglob("/storage/workflows/*.json"))]
    return render_template_string(workflows_ui_template, workflows=workflows, no_workflows_message="No Workflows or Mappings Found.")

@app.route('/<workflow_name>')
def serve_raw_file(workflow_name):
    return send_file(f"/storage/workflows/{workflow_name}", mimetype='application/json')

if __name__ == "__main__":
    app.run(host="0.0.0.0")
