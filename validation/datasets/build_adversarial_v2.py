"""Syntax-only repair of v0.2-L inputs. Same cases and labels, not a fresh holdout."""
import json
import re
from validation.datasets.build_adversarial import build, typed_rules


def compatible_rules(family, facts, text):
    context=typed_rules(family,facts,text)
    values={k:v["value"] for k,v in context["structured_facts"].items()}
    if family=="path_scope":
        values["parent_component_count"]=facts["path"].split("/").count("..")
        context["structured_facts"]["parent_component_count"]={"key":"parent_component_count","value":values["parent_component_count"]}
    for rule in context["policy_rules"]:
        predicate=rule["predicate"]
        if family=="path_scope": predicate=predicate.replace("not ('..' in fact.path_parts)","fact.parent_component_count == 0")
        # The public grammar accepts path OP literal, not path OP another path.
        # Bind RHS values from the supplied case; never substitute oracle outcomes.
        predicate=re.sub(r"(<=|>=|==|!=|<|>|\bin\b)\s+fact\.([A-Za-z_]\w*)",
            lambda m:m.group(1)+" "+json.dumps(values[m.group(2)],ensure_ascii=True),predicate)
        rule["predicate"]=predicate
    return context


if __name__=="__main__":
    build(version="adversarial-v0.2-L-syntax2",mapper=compatible_rules)
