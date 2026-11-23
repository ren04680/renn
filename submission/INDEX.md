# Submission — Hospital Agent OS

Assembled 2026-11-23 05:39.

| Item | Location | Status |
|---|---|---|
| Source code (all tracked files) | `source.zip` | ✅ 111 files |
| Dataset (HIS tables + triage dataset) | `data/*.csv` | ✅ 11 CSVs |
| Model file | `models/triage_classifier.joblib` | ✅ TF-IDF + Logistic Regression |
| Model metrics | `models/metrics.json`, `models/confusion_matrix.png` | ✅ specialty acc 0.970, macro-F1 0.970; emergency recall 1.000 |
| Scenario test results | `test_results.md / .csv / .json` | ✅ 20/20 passed |
| Step-by-step screenshots | `screenshots/NN_*.png` | ✅ 41 screenshots |
| README (setup, architecture, Mermaid diagrams) | `README.md` | ✅ |
| Live demo script + viva Q&A | `DEMO_SCRIPT.md` | ✅ |
| Design decisions log | `DECISIONS.md` | ✅ |

## Screenshots

1. `01_home_patient_P001.png`
2. `02_normal_request_tool_choice_and_proposal.png`
3. `03_normal_request_why_each_tool.png`
4. `04_normal_request_booked.png`
5. `05_intake_memory_aware_asks_only_the_day.png`
6. `06_intake_answered_usual_doctor_evening_card.png`
7. `07_memory_recall_usual_doctor.png`
8. `08_memory_booked_usual_doctor_evening.png`
9. `09_multigoal_decomposition.png`
10. `10_multigoal_combined_proposal_one_approval.png`
11. `11_multigoal_booked_both.png`
12. `12_blackboard_multigoal_subtasks.png`
13. `13_critic_catches_injected_fault_REVISE.png`
14. `14_critic_corrected_proposal_with_disclosure.png`
15. `15_critic_corrected_booked.png`
16. `16_ops_before_event.png`
17. `17_ops_after_doctor_cancels_block.png`
18. `18_proactive_event_watcher_no_prompt.png`
19. `19_proactive_memory_based_alternatives.png`
20. `20_proactive_offer_card_P001.png`
21. `21_proactive_offer_confirmed.png`
22. `22_proactive_offer_P023_teleconsult_preference.png`
23. `23_ops_slot_freed_waitlist.png`
24. `24_waitlist_offer_P031.png`
25. `25_waitlist_offer_confirmed.png`
26. `26_emergency_escalation.png`
27. `27_intake_guest_asks_day_time_area.png`
28. `28_intake_guest_answered_proposal.png`
29. `29_clarification_question.png`
30. `30_clarification_answered_proposal.png`
31. `31_relaxation_widen_area_disclosed.png`
32. `32_relaxation_teleconsult_disclosed.png`
33. `33_hinglish_triage_classifier.png`
34. `34_register_new_patient_form.png`
35. `35_registered_patient_welcome.png`
36. `36_waitlisted_after_full_ladder.png`
37. `37_billing_answer_from_data.png`
38. `38_ops_final_state_outbox.png`
39. `39_blackboard_audit_trail.png`
40. `40_metrics_scenarios_and_classifier.png`
41. `41_metrics_confusion_matrix.png`
