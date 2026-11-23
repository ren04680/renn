# Submission — Hospital Agent OS

Assembled 2026-11-23 04:34.

| Item | Location | Status |
|---|---|---|
| Source code (all tracked files) | `source.zip` | ✅ 108 files |
| Dataset (HIS tables + triage dataset) | `data/*.csv` | ✅ 11 CSVs |
| Model file | `models/triage_classifier.joblib` | ✅ TF-IDF + Logistic Regression |
| Model metrics | `models/metrics.json`, `models/confusion_matrix.png` | ✅ specialty acc 0.970, macro-F1 0.970; emergency recall 1.000 |
| Scenario test results | `test_results.md / .csv / .json` | ✅ 18/18 passed |
| Step-by-step screenshots | `screenshots/NN_*.png` | ✅ 35 screenshots |
| README (setup, architecture, Mermaid diagrams) | `README.md` | ✅ |
| Live demo script + viva Q&A | `DEMO_SCRIPT.md` | ✅ |
| Design decisions log | `DECISIONS.md` | ✅ |

## Screenshots

1. `01_home_patient_P001.png`
2. `02_normal_request_tool_choice_and_proposal.png`
3. `03_normal_request_why_each_tool.png`
4. `04_normal_request_booked.png`
5. `05_memory_recall_usual_doctor.png`
6. `06_memory_booked_usual_doctor_evening.png`
7. `07_multigoal_decomposition.png`
8. `08_multigoal_combined_proposal_one_approval.png`
9. `09_multigoal_booked_both.png`
10. `10_blackboard_multigoal_subtasks.png`
11. `11_critic_catches_injected_fault_REVISE.png`
12. `12_critic_corrected_proposal_with_disclosure.png`
13. `13_critic_corrected_booked.png`
14. `14_ops_before_event.png`
15. `15_ops_after_doctor_cancels_block.png`
16. `16_proactive_event_watcher_no_prompt.png`
17. `17_proactive_memory_based_alternatives.png`
18. `18_proactive_offer_card_P001.png`
19. `19_proactive_offer_confirmed.png`
20. `20_proactive_offer_P023_teleconsult_preference.png`
21. `21_ops_slot_freed_waitlist.png`
22. `22_waitlist_offer_P031.png`
23. `23_waitlist_offer_confirmed.png`
24. `24_emergency_escalation.png`
25. `25_clarification_question.png`
26. `26_clarification_answered_proposal.png`
27. `27_relaxation_widen_area_disclosed.png`
28. `28_relaxation_teleconsult_disclosed.png`
29. `29_hinglish_triage_classifier.png`
30. `30_waitlisted_after_full_ladder.png`
31. `31_billing_answer_from_data.png`
32. `32_ops_final_state_outbox.png`
33. `33_blackboard_audit_trail.png`
34. `34_metrics_scenarios_and_classifier.png`
35. `35_metrics_confusion_matrix.png`
