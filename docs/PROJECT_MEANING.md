# A visual interface for 3D annotation

WireSight asks how a vision-language observer can perform a 3D point task through task-relevant visual observations while preserving exact original-record identity locally. Wires are the first demonstrated task.

The five main traces are discovered and separated primarily in the top-down height-colored projection. Side and axial views provide evidence about sag, supports, overlap and contacts. XY positions determine image locations; Z affects brightness. A top-view pixel retains the highest visible record. Depth and source-record mappings remain in the executor; the VLM does not receive a separate depth channel in this historical run.

The renderer supplies geometric evidence. The observer identifies task objects, associates fragments, chooses additional views/zooms, specifies image regions and judges support, contradiction or insufficient evidence. The executor applies those explicit selections, preserves unknown labels, and verifies replay/export consistency.

The research direction is task-driven compression of **model observations**: the complete original cloud remains local, while projected views and local inspection supply the model with evidence for a task. The current release does not quantify token savings or establish an optimal observation/accuracy trade-off.

The inspected development-scene point result demonstrates a feasible observation-to-label loop. It does not establish VLM superiority over geometric baselines, unattended repeatability, independent instance identity, endpoint/length completeness or cross-scene generalization. Presentation should make the demonstrated capability easy to see and the evaluation scope easy to check.
