# FiNER-139 — consolidated re-run, dev split, 40 docs, 165 scorable gold mentions

## Rung 0 per draw (span-exact / overlap; F1 = score_run with exclusions)
| draw | spans | det P/R/F1 exact | coding exact | F1 exact [CI] | det F1 overlap | coding overlap | F1 overlap | sha256(r0) |
|---|---|---|---|---|---|---|---|---|
| rerun-finer-d0 | 304 | 0.388/0.715/0.503 | 0.390 | **0.196** [0.105–0.282] | 0.529 | 0.395 | 0.209 | `3cde146c` |
| rerun-finer-d1 | 304 | 0.388/0.715/0.503 | 0.390 | **0.196** [0.105–0.282] | 0.529 | 0.395 | 0.209 | `3cde146c` |
| rerun-finer-d2 | 304 | 0.388/0.715/0.503 | 0.390 | **0.196** [0.105–0.282] | 0.529 | 0.395 | 0.209 | `3cde146c` |

## Error budget per draw (exact; one denominator: the scorable gold set)
| draw | gold | matched | missed (find) | invented | on menu | lost retrieval | correct | lost pick | pick loss by lane |
|---|---|---|---|---|---|---|---|---|---|
| rerun-finer-d0 | 165 | 118 | 47 | 186 | 118 | 0 | 46 | 72 | {'model': 56, 'fallback': 16} |
| rerun-finer-d1 | 165 | 118 | 47 | 186 | 118 | 0 | 46 | 72 | {'model': 56, 'fallback': 16} |
| rerun-finer-d2 | 165 | 118 | 47 | 186 | 118 | 0 | 46 | 72 | {'model': 56, 'fallback': 16} |

## Rung 1 lanes per draw (n / correct exact % / on no gold / correct % on overlap-matched)
- rerun-finer-d0: BAND: 301 / 15.28% / 174 / 38.58%; REJECT: 3 / 0.0% / 3 / 0.0%
- rerun-finer-d1: BAND: 301 / 15.28% / 174 / 38.58%; REJECT: 3 / 0.0% / 3 / 0.0%
- rerun-finer-d2: BAND: 301 / 15.28% / 174 / 38.58%; REJECT: 3 / 0.0% / 3 / 0.0%

## Rung 3 by rung 1 lane
- rerun-finer-d0: by lane {'BAND': {'unanimous': 87, 'tie': 65, 'changed': 74, 'single_sample': 7, 'split': 61, 'not_resampled': 7}, 'REJECT': {'not_resampled': 3}}; changed 74, correct destroyed 3, gained 9, net +6; not_resampled had been {'unmatched': 9, 'correct': 1}
    - FINER.test.0103#0 [BAND] RevenueFromContractWithCustomerExcludingAssessedTax -> Revenues votes {'AccrualForEnvironmentalLossContingencies': 1, 'Revenues': 2}: incorrect -> incorrect
    - FINER.test.0103#1 [BAND] RevenueFromContractWithCustomerExcludingAssessedTax -> Revenues votes {'AccrualForEnvironmentalLossContingencies': 1, 'Revenues': 2}: incorrect -> incorrect
    - FINER.test.0103#2 [BAND] RevenueFromContractWithCustomerExcludingAssessedTax -> Revenues votes {'AccrualForEnvironmentalLossContingencies': 1, 'Revenues': 2}: unmatched -> unmatched
    - FINER.test.0103#3 [BAND] RevenueFromContractWithCustomerExcludingAssessedTax -> AccrualForEnvironmentalLossContingencies votes {'AccrualForEnvironmentalLossContingencies': 2, 'Revenues': 1}: unmatched -> unmatched
    - FINER.test.0059#11 [BAND] Depreciation -> AmortizationOfIntangibleAssets votes {'Depreciation': 1, 'AmortizationOfIntangibleAssets': 2}: incorrect -> correct
    - FINER.test.0059#12 [BAND] Depreciation -> AmortizationOfIntangibleAssets votes {'Depreciation': 1, 'AmortizationOfIntangibleAssets': 2}: incorrect -> correct
    - FINER.test.0073#1 [BAND] AccrualForEnvironmentalLossContingencies -> SaleOfStockPricePerShare votes {'AccrualForEnvironmentalLossContingencies': 1, 'SaleOfStockPricePerShare': 2}: unmatched -> unmatched
    - FINER.test.0025#0 [BAND] DebtInstrumentInterestRateStatedPercentage -> DebtInstrumentInterestRateEffectivePercentage votes {'DebtInstrumentInterestRateEffectivePercentage': 3}: unmatched -> unmatched
    - FINER.test.0025#1 [BAND] DebtInstrumentInterestRateStatedPercentage -> DebtInstrumentInterestRateEffectivePercentage votes {'DebtInstrumentInterestRateEffectivePercentage': 3}: unmatched -> unmatched
    - FINER.test.0025#3 [BAND] MinorityInterestOwnershipPercentageByNoncontrollingOwners -> ConcentrationRiskPercentage1 votes {'AccrualForEnvironmentalLossContingencies': 1, 'ConcentrationRiskPercentage1': 2}: unmatched -> unmatched
    - FINER.test.0025#4 [BAND] IncomeLossFromEquityMethodInvestments -> AccrualForEnvironmentalLossContingencies votes {'AccrualForEnvironmentalLossContingencies': 2, 'DebtInstrumentFaceAmount': 1}: incorrect -> incorrect
    - FINER.test.0047#0 [BAND] AccrualForEnvironmentalLossContingencies -> DebtInstrumentCarryingAmount votes {'DebtInstrumentCarryingAmount': 3}: unmatched -> unmatched
    - FINER.test.0047#1 [BAND] MinorityInterestOwnershipPercentageByNoncontrollingOwners -> BusinessAcquisitionEquityInterestsIssuedOrIssuableNumberOfSharesIssued votes {'BusinessAcquisitionEquityInterestsIssuedOrIssuableNumberOfSharesIssued': 2, 'BusinessAcquisitionPercentageOfVotingInterestsAcquired': 1}: unmatched -> unmatched
    - FINER.test.0047#2 [BAND] MinorityInterestOwnershipPercentageByNoncontrollingOwners -> BusinessAcquisitionPercentageOfVotingInterestsAcquired votes {'BusinessAcquisitionPercentageOfVotingInterestsAcquired': 2, 'AccrualForEnvironmentalLossContingencies': 1}: correct -> incorrect
    - FINER.test.0047#3 [BAND] MinorityInterestOwnershipPercentageByNoncontrollingOwners -> BusinessAcquisitionPercentageOfVotingInterestsAcquired votes {'BusinessAcquisitionPercentageOfVotingInterestsAcquired': 2, 'AccrualForEnvironmentalLossContingencies': 1}: incorrect -> incorrect
    - FINER.test.0069#0 [BAND] DebtInstrumentFaceAmount -> AccrualForEnvironmentalLossContingencies votes {'AccrualForEnvironmentalLossContingencies': 2, 'CONCEPT_LESS': 1}: unmatched -> unmatched
    - FINER.test.0023#1 [BAND] BusinessAcquisitionPercentageOfVotingInterestsAcquired -> ConcentrationRiskPercentage1 votes {'DebtInstrumentFaceAmount': 1, 'ConcentrationRiskPercentage1': 2}: unmatched -> unmatched
    - FINER.test.0023#3 [BAND] BusinessAcquisitionPercentageOfVotingInterestsAcquired -> ConcentrationRiskPercentage1 votes {'ConcentrationRiskPercentage1': 3}: unmatched -> unmatched
    - FINER.test.0023#5 [BAND] BusinessAcquisitionPercentageOfVotingInterestsAcquired -> ConcentrationRiskPercentage1 votes {'DebtInstrumentFaceAmount': 1, 'ConcentrationRiskPercentage1': 2}: unmatched -> unmatched
    - FINER.test.0016#0 [BAND] AccrualForEnvironmentalLossContingencies -> CONCEPT_LESS votes {'AccrualForEnvironmentalLossContingencies': 1, 'CONCEPT_LESS': 2}: unmatched -> unmatched
    - FINER.test.0016#1 [BAND] AccrualForEnvironmentalLossContingencies -> DebtInstrumentBasisSpreadOnVariableRate1 votes {'DebtInstrumentBasisSpreadOnVariableRate1': 2, 'DebtInstrumentInterestRateEffectivePercentage': 1}: unmatched -> unmatched
    - FINER.test.0016#5 [BAND] DebtInstrumentFaceAmount -> CONCEPT_LESS votes {'AccrualForEnvironmentalLossContingencies': 1, 'CONCEPT_LESS': 2}: unmatched -> unmatched
    - FINER.test.0085#4 [BAND] AccrualForEnvironmentalLossContingencies -> InterestExpense votes {'InterestExpense': 3}: incorrect -> correct
    - FINER.test.0076#0 [BAND] CONCEPT_LESS -> BusinessAcquisitionEquityInterestsIssuedOrIssuableNumberOfSharesIssued votes {'BusinessAcquisitionEquityInterestsIssuedOrIssuableNumberOfSharesIssued': 3}: unmatched -> unmatched
    - FINER.test.0008#0 [BAND] LineOfCredit -> DebtInstrumentCarryingAmount votes {'DebtInstrumentCarryingAmount': 3}: unmatched -> unmatched
    - FINER.test.0008#1 [BAND] LineOfCredit -> DebtInstrumentCarryingAmount votes {'DebtInstrumentCarryingAmount': 2, 'DebtInstrumentInterestRateEffectivePercentage': 1}: unmatched -> unmatched
    - FINER.test.0008#4 [BAND] LineOfCredit -> DebtInstrumentCarryingAmount votes {'DebtInstrumentCarryingAmount': 3}: unmatched -> unmatched
    - FINER.test.0008#17 [BAND] DeferredFinanceCostsGross -> DebtInstrumentCarryingAmount votes {'DebtInstrumentCarryingAmount': 3}: incorrect -> incorrect
    - FINER.test.0008#18 [BAND] DeferredFinanceCostsGross -> DebtInstrumentCarryingAmount votes {'DebtInstrumentCarryingAmount': 3}: incorrect -> incorrect
    - FINER.test.0043#0 [BAND] OperatingLeaseLiability -> DebtInstrumentCarryingAmount votes {'DebtInstrumentCarryingAmount': 2, 'AccrualForEnvironmentalLossContingencies': 1}: unmatched -> unmatched
    - FINER.test.0043#1 [BAND] OperatingLeaseLiability -> DebtInstrumentCarryingAmount votes {'DebtInstrumentCarryingAmount': 3}: unmatched -> unmatched
    - FINER.test.0084#6 [BAND] AccrualForEnvironmentalLossContingencies -> RestructuringAndRelatedCostExpectedCost1 votes {'RestructuringAndRelatedCostExpectedCost1': 2, 'CommonStockDividendsPerShareDeclared': 1}: unmatched -> unmatched
    - FINER.test.0084#7 [BAND] RestructuringAndRelatedCostExpectedCost1 -> DebtInstrumentBasisSpreadOnVariableRate1 votes {'AccrualForEnvironmentalLossContingencies': 1, 'DebtInstrumentBasisSpreadOnVariableRate1': 2}: unmatched -> unmatched
    - FINER.test.0084#8 [BAND] RestructuringAndRelatedCostExpectedCost1 -> RestructuringCharges votes {'RestructuringCharges': 2, 'DerivativeNotionalAmount': 1}: incorrect -> correct
    - FINER.test.0084#9 [BAND] RestructuringAndRelatedCostExpectedCost1 -> RestructuringCharges votes {'RestructuringCharges': 2, 'BusinessAcquisitionEquityInterestsIssuedOrIssuableNumberOfSharesIssued': 1}: incorrect -> correct
    - FINER.test.0084#10 [BAND] RestructuringAndRelatedCostExpectedCost1 -> RestructuringCharges votes {'RestructuringCharges': 2, 'AccrualForEnvironmentalLossContingencies': 1}: incorrect -> correct
    - FINER.test.0098#0 [BAND] DebtInstrumentFaceAmount -> StockRepurchaseProgramAuthorizedAmount1 votes {'StockRepurchaseProgramAuthorizedAmount1': 3}: incorrect -> correct
    - FINER.test.0098#2 [BAND] BusinessAcquisitionEquityInterestsIssuedOrIssuableNumberOfSharesIssued -> StockRepurchasedAndRetiredDuringPeriodShares votes {'StockRepurchasedAndRetiredDuringPeriodShares': 3}: unmatched -> unmatched
    - FINER.test.0098#4 [BAND] DebtInstrumentFaceAmount -> StockRepurchaseProgramAuthorizedAmount1 votes {'StockRepurchaseProgramAuthorizedAmount1': 3}: incorrect -> correct
    - FINER.test.0098#6 [BAND] CommonStockDividendsPerShareDeclared -> AccrualForEnvironmentalLossContingencies votes {'CommonStockDividendsPerShareDeclared': 1, 'AccrualForEnvironmentalLossContingencies': 2}: unmatched -> unmatched
    - FINER.test.0044#3 [BAND] ConcentrationRiskPercentage1 -> MinorityInterestOwnershipPercentageByNoncontrollingOwners votes {'MinorityInterestOwnershipPercentageByNoncontrollingOwners': 2, 'NumberOfOperatingSegments': 1}: unmatched -> unmatched
    - FINER.test.0044#4 [BAND] ConcentrationRiskPercentage1 -> MinorityInterestOwnershipPercentageByNoncontrollingOwners votes {'MinorityInterestOwnershipPercentageByNoncontrollingOwners': 2, 'ConcentrationRiskPercentage1': 1}: incorrect -> correct
    - FINER.test.0044#5 [BAND] ConcentrationRiskPercentage1 -> MinorityInterestOwnershipPercentageByNoncontrollingOwners votes {'MinorityInterestOwnershipPercentageByNoncontrollingOwners': 2, 'ConcentrationRiskPercentage1': 1}: unmatched -> unmatched
    - FINER.test.0044#7 [BAND] ConcentrationRiskPercentage1 -> CommonStockSharesOutstanding votes {'CommonStockSharesOutstanding': 2}: unmatched -> unmatched
    - FINER.test.0044#8 [BAND] ConcentrationRiskPercentage1 -> MinorityInterestOwnershipPercentageByNoncontrollingOwners votes {'ConcentrationRiskPercentage1': 1, 'MinorityInterestOwnershipPercentageByNoncontrollingOwners': 2}: incorrect -> incorrect
    - FINER.test.0080#6 [BAND] DebtInstrumentInterestRateEffectivePercentage -> AccrualForEnvironmentalLossContingencies votes {'DebtInstrumentInterestRateEffectivePercentage': 1, 'AccrualForEnvironmentalLossContingencies': 2}: unmatched -> unmatched
    - FINER.test.0037#4 [BAND] DebtInstrumentInterestRateEffectivePercentage -> DebtInstrumentInterestRateStatedPercentage votes {'DebtInstrumentInterestRateStatedPercentage': 3}: incorrect -> incorrect
    - FINER.test.0037#5 [BAND] DebtInstrumentInterestRateEffectivePercentage -> DebtInstrumentInterestRateStatedPercentage votes {'DebtInstrumentInterestRateStatedPercentage': 3}: incorrect -> incorrect
    - FINER.test.0037#12 [BAND] CONCEPT_LESS -> AccrualForEnvironmentalLossContingencies votes {'AccrualForEnvironmentalLossContingencies': 3}: unmatched -> unmatched
    - FINER.test.0037#13 [BAND] CONCEPT_LESS -> AccrualForEnvironmentalLossContingencies votes {'AccrualForEnvironmentalLossContingencies': 3}: unmatched -> unmatched
    - FINER.test.0010#2 [BAND] DebtInstrumentCarryingAmount -> DebtInstrumentRedemptionPricePercentage votes {'DebtInstrumentRedemptionPricePercentage': 3}: unmatched -> unmatched
    - FINER.test.0024#2 [BAND] DebtInstrumentRedemptionPricePercentage -> DebtInstrumentBasisSpreadOnVariableRate1 votes {'DebtInstrumentBasisSpreadOnVariableRate1': 2, 'DebtInstrumentRedemptionPricePercentage': 1}: unmatched -> unmatched
    - FINER.test.0024#3 [BAND] DebtInstrumentRedemptionPricePercentage -> DebtInstrumentBasisSpreadOnVariableRate1 votes {'DebtInstrumentBasisSpreadOnVariableRate1': 2, 'DebtInstrumentRedemptionPricePercentage': 1}: unmatched -> unmatched
    - FINER.test.0024#4 [BAND] Revenues -> AccrualForEnvironmentalLossContingencies votes {'Revenues': 1, 'AccrualForEnvironmentalLossContingencies': 2}: incorrect -> incorrect
    - FINER.test.0024#10 [BAND] MinorityInterestOwnershipPercentageByNoncontrollingOwners -> ConcentrationRiskPercentage1 votes {'ConcentrationRiskPercentage1': 2, 'Revenues': 1}: unmatched -> unmatched
    - FINER.test.0024#11 [BAND] MinorityInterestOwnershipPercentageByNoncontrollingOwners -> ConcentrationRiskPercentage1 votes {'ConcentrationRiskPercentage1': 2, 'DebtInstrumentFaceAmount': 1}: unmatched -> unmatched
    - FINER.test.0024#13 [BAND] MinorityInterestOwnershipPercentageByNoncontrollingOwners -> ConcentrationRiskPercentage1 votes {'ConcentrationRiskPercentage1': 2, 'DebtInstrumentFaceAmount': 1}: unmatched -> unmatched
    - FINER.test.0024#14 [BAND] AccrualForEnvironmentalLossContingencies -> DebtInstrumentRedemptionPricePercentage votes {'DebtInstrumentRedemptionPricePercentage': 2, 'DebtInstrumentCarryingAmount': 1}: unmatched -> unmatched
    - FINER.test.0104#1 [BAND] Revenues -> RevenueFromContractWithCustomerExcludingAssessedTax votes {'RevenueFromContractWithCustomerExcludingAssessedTax': 2, 'RevenueRemainingPerformanceObligation': 1}: unmatched -> unmatched
    - FINER.test.0104#2 [BAND] Revenues -> RevenueFromContractWithCustomerExcludingAssessedTax votes {'RevenueFromContractWithCustomerExcludingAssessedTax': 2, 'RevenueRemainingPerformanceObligation': 1}: incorrect -> incorrect
    - FINER.test.0104#3 [BAND] Revenues -> RevenueFromContractWithCustomerExcludingAssessedTax votes {'RevenueFromContractWithCustomerExcludingAssessedTax': 2, 'RevenueRemainingPerformanceObligation': 1}: incorrect -> incorrect
    - FINER.test.0104#9 [BAND] BusinessCombinationConsiderationTransferred1 -> BusinessCombinationAcquisitionRelatedCosts votes {'BusinessCombinationAcquisitionRelatedCosts': 2, 'CashAndCashEquivalentsFairValueDisclosure': 1}: unmatched -> unmatched
    - FINER.test.0093#8 [BAND] AccrualForEnvironmentalLossContingencies -> LineOfCredit votes {'LineOfCredit': 3}: incorrect -> incorrect
    - FINER.test.0013#14 [BAND] DebtInstrumentConvertibleConversionPrice1 -> DebtInstrumentUnamortizedDiscount votes {'DebtInstrumentUnamortizedDiscount': 3}: unmatched -> unmatched
    - FINER.test.0013#19 [BAND] InterestExpense -> DeferredFinanceCostsNet votes {'DeferredFinanceCostsNet': 2, 'DeferredFinanceCostsGross': 1}: incorrect -> incorrect
    - FINER.test.0013#20 [BAND] DebtInstrumentInterestRateEffectivePercentage -> DebtWeightedAverageInterestRate votes {'DebtInstrumentInterestRateEffectivePercentage': 1, 'DebtWeightedAverageInterestRate': 2}: correct -> incorrect
    - FINER.test.0013#24 [BAND] DeferredFinanceCostsGross -> DebtInstrumentUnamortizedDiscount votes {'DebtInstrumentUnamortizedDiscount': 3}: unmatched -> unmatched
    - FINER.test.0013#25 [BAND] DeferredFinanceCostsGross -> DebtInstrumentUnamortizedDiscount votes {'DebtInstrumentUnamortizedDiscount': 3}: unmatched -> unmatched
    - FINER.test.0013#29 [BAND] DebtWeightedAverageInterestRate -> DebtInstrumentInterestRateEffectivePercentage votes {'DebtInstrumentInterestRateEffectivePercentage': 2, 'DebtWeightedAverageInterestRate': 1}: correct -> incorrect
    - FINER.test.0052#0 [BAND] DebtInstrumentRedemptionPricePercentage -> AccrualForEnvironmentalLossContingencies votes {'AccrualForEnvironmentalLossContingencies': 2, 'ConcentrationRiskPercentage1': 1}: unmatched -> unmatched
    - FINER.test.0052#1 [BAND] DebtInstrumentRedemptionPricePercentage -> AccrualForEnvironmentalLossContingencies votes {'AccrualForEnvironmentalLossContingencies': 2, 'ConcentrationRiskPercentage1': 1}: unmatched -> unmatched
    - FINER.test.0052#16 [BAND] DebtWeightedAverageInterestRate -> AccrualForEnvironmentalLossContingencies votes {'AccrualForEnvironmentalLossContingencies': 2, 'DebtInstrumentInterestRateEffectivePercentage': 1}: unmatched -> unmatched
    - FINER.test.0052#19 [BAND] DebtWeightedAverageInterestRate -> DebtInstrumentInterestRateEffectivePercentage votes {'DebtInstrumentInterestRateEffectivePercentage': 3}: incorrect -> incorrect
    - FINER.test.0052#22 [BAND] AccrualForEnvironmentalLossContingencies -> LineOfCreditFacilityCommitmentFeePercentage votes {'LineOfCreditFacilityCommitmentFeePercentage': 2, 'DebtInstrumentInterestRateEffectivePercentage': 1}: incorrect -> incorrect
- rerun-finer-d1: by lane {'BAND': {'unanimous': 64, 'changed': 83, 'split': 55, 'tie': 74, 'single_sample': 11, 'not_resampled': 14}, 'REJECT': {'not_resampled': 3}}; changed 83, correct destroyed 2, gained 10, net +8; not_resampled had been {'unmatched': 15, 'correct': 1, 'incorrect': 1}
    - FINER.test.0057#8 [BAND] BusinessAcquisitionEquityInterestsIssuedOrIssuableNumberOfSharesIssued -> AccrualForEnvironmentalLossContingencies votes {'AccrualForEnvironmentalLossContingencies': 3}: unmatched -> unmatched
    - FINER.test.0103#0 [BAND] RevenueFromContractWithCustomerExcludingAssessedTax -> Revenues votes {'Revenues': 3}: incorrect -> incorrect
    - FINER.test.0103#1 [BAND] RevenueFromContractWithCustomerExcludingAssessedTax -> Revenues votes {'Revenues': 3}: incorrect -> incorrect
    - FINER.test.0103#2 [BAND] RevenueFromContractWithCustomerExcludingAssessedTax -> Revenues votes {'Revenues': 3}: unmatched -> unmatched
    - FINER.test.0103#3 [BAND] RevenueFromContractWithCustomerExcludingAssessedTax -> AccrualForEnvironmentalLossContingencies votes {'Revenues': 1, 'AccrualForEnvironmentalLossContingencies': 2}: unmatched -> unmatched
    - FINER.test.0003#15 [BAND] CashAndCashEquivalentsFairValueDisclosure -> ConcentrationRiskPercentage1 votes {'ConcentrationRiskPercentage1': 2, 'CashAndCashEquivalentsFairValueDisclosure': 1}: incorrect -> correct
    - FINER.test.0003#16 [BAND] BusinessCombinationContingentConsiderationLiability -> ConcentrationRiskPercentage1 votes {'ConcentrationRiskPercentage1': 2, 'AccrualForEnvironmentalLossContingencies': 1}: unmatched -> unmatched
    - FINER.test.0059#0 [BAND] AccrualForEnvironmentalLossContingencies -> DebtInstrumentFaceAmount votes {'DebtInstrumentFaceAmount': 2, 'AccrualForEnvironmentalLossContingencies': 1}: unmatched -> unmatched
    - FINER.test.0059#1 [BAND] AccrualForEnvironmentalLossContingencies -> DeferredFinanceCostsNet votes {'DeferredFinanceCostsNet': 2, 'AccrualForEnvironmentalLossContingencies': 1}: unmatched -> unmatched
    - FINER.test.0059#2 [BAND] AccrualForEnvironmentalLossContingencies -> AmortizationOfFinancingCosts votes {'AmortizationOfFinancingCosts': 2, 'AccrualForEnvironmentalLossContingencies': 1}: unmatched -> unmatched
    - FINER.test.0059#5 [BAND] AccrualForEnvironmentalLossContingencies -> ConcentrationRiskPercentage1 votes {'AccrualForEnvironmentalLossContingencies': 1, 'ConcentrationRiskPercentage1': 2}: unmatched -> unmatched
    - FINER.test.0059#11 [BAND] Depreciation -> AmortizationOfIntangibleAssets votes {'AmortizationOfIntangibleAssets': 2, 'Depreciation': 1}: incorrect -> correct
    - FINER.test.0059#12 [BAND] Depreciation -> AmortizationOfIntangibleAssets votes {'AmortizationOfIntangibleAssets': 2, 'Depreciation': 1}: incorrect -> correct
    - FINER.test.0073#1 [BAND] AccrualForEnvironmentalLossContingencies -> ClassOfWarrantOrRightExercisePriceOfWarrantsOrRights1 votes {'AccrualForEnvironmentalLossContingencies': 1, 'ClassOfWarrantOrRightExercisePriceOfWarrantsOrRights1': 2}: unmatched -> unmatched
    - FINER.test.0022#0 [BAND] AccrualForEnvironmentalLossContingencies -> OperatingLeaseWeightedAverageDiscountRatePercent votes {'AccrualForEnvironmentalLossContingencies': 1, 'OperatingLeaseWeightedAverageDiscountRatePercent': 2}: incorrect -> incorrect
    - FINER.test.0022#5 [BAND] AccrualForEnvironmentalLossContingencies -> DebtInstrumentFaceAmount votes {'AccrualForEnvironmentalLossContingencies': 1, 'DebtInstrumentFaceAmount': 2}: unmatched -> unmatched
    - FINER.test.0025#0 [BAND] DebtInstrumentInterestRateStatedPercentage -> DebtInstrumentInterestRateEffectivePercentage votes {'DebtInstrumentInterestRateStatedPercentage': 1, 'DebtInstrumentInterestRateEffectivePercentage': 2}: unmatched -> unmatched
    - FINER.test.0025#1 [BAND] DebtInstrumentInterestRateStatedPercentage -> DebtInstrumentInterestRateEffectivePercentage votes {'DebtInstrumentInterestRateStatedPercentage': 1, 'DebtInstrumentInterestRateEffectivePercentage': 2}: unmatched -> unmatched
    - FINER.test.0025#3 [BAND] MinorityInterestOwnershipPercentageByNoncontrollingOwners -> BusinessAcquisitionPercentageOfVotingInterestsAcquired votes {'AccrualForEnvironmentalLossContingencies': 1, 'BusinessAcquisitionPercentageOfVotingInterestsAcquired': 2}: unmatched -> unmatched
    - FINER.test.0025#9 [BAND] DebtInstrumentCarryingAmount -> DebtInstrumentFaceAmount votes {'DebtInstrumentCarryingAmount': 1, 'DebtInstrumentFaceAmount': 2}: unmatched -> unmatched
    - FINER.test.0025#10 [BAND] DebtInstrumentCarryingAmount -> RepaymentsOfDebt votes {'DebtInstrumentCarryingAmount': 1, 'RepaymentsOfDebt': 2}: unmatched -> unmatched
    - FINER.test.0047#0 [BAND] AccrualForEnvironmentalLossContingencies -> DebtInstrumentCarryingAmount votes {'DebtInstrumentCarryingAmount': 3}: unmatched -> unmatched
    - FINER.test.0047#6 [BAND] AccrualForEnvironmentalLossContingencies -> EffectiveIncomeTaxRateContinuingOperations votes {'EffectiveIncomeTaxRateContinuingOperations': 2, 'AccrualForEnvironmentalLossContingencies': 1}: incorrect -> correct
    - FINER.test.0047#9 [BAND] IncomeLossFromEquityMethodInvestments -> AccrualForEnvironmentalLossContingencies votes {'AccrualForEnvironmentalLossContingencies': 2, 'EffectiveIncomeTaxRateContinuingOperations': 1}: unmatched -> unmatched
    - FINER.test.0069#0 [BAND] DebtInstrumentFaceAmount -> AccrualForEnvironmentalLossContingencies votes {'AccrualForEnvironmentalLossContingencies': 2, 'DebtInstrumentFaceAmount': 1}: unmatched -> unmatched
    - FINER.test.0023#1 [BAND] BusinessAcquisitionPercentageOfVotingInterestsAcquired -> ConcentrationRiskPercentage1 votes {'ConcentrationRiskPercentage1': 3}: unmatched -> unmatched
    - FINER.test.0023#3 [BAND] BusinessAcquisitionPercentageOfVotingInterestsAcquired -> ConcentrationRiskPercentage1 votes {'ConcentrationRiskPercentage1': 3}: unmatched -> unmatched
    - FINER.test.0023#5 [BAND] BusinessAcquisitionPercentageOfVotingInterestsAcquired -> ConcentrationRiskPercentage1 votes {'ConcentrationRiskPercentage1': 3}: unmatched -> unmatched
    - FINER.test.0075#0 [BAND] ConcentrationRiskPercentage1 -> AccrualForEnvironmentalLossContingencies votes {'ConcentrationRiskPercentage1': 1, 'AccrualForEnvironmentalLossContingencies': 2}: unmatched -> unmatched
    - FINER.test.0085#4 [BAND] AccrualForEnvironmentalLossContingencies -> InterestExpense votes {'InterestExpense': 2, 'InterestExpenseDebt': 1}: incorrect -> correct
    - FINER.test.0008#6 [BAND] DebtInstrumentCarryingAmount -> LineOfCredit votes {'LineOfCredit': 3}: incorrect -> incorrect
    - FINER.test.0008#17 [BAND] DeferredFinanceCostsGross -> DebtInstrumentCarryingAmount votes {'DebtInstrumentCarryingAmount': 2, 'DeferredFinanceCostsNet': 1}: incorrect -> incorrect
    - FINER.test.0008#18 [BAND] DeferredFinanceCostsGross -> DeferredFinanceCostsNet votes {'DeferredFinanceCostsNet': 2, 'DebtInstrumentCarryingAmount': 1}: incorrect -> correct
    - FINER.test.0107#1 [BAND] AccrualForEnvironmentalLossContingencies -> DebtInstrumentInterestRateEffectivePercentage votes {'DebtInstrumentInterestRateEffectivePercentage': 2, 'AccrualForEnvironmentalLossContingencies': 1}: unmatched -> unmatched
    - FINER.test.0043#0 [BAND] OperatingLeaseLiability -> DebtInstrumentCarryingAmount votes {'DebtInstrumentCarryingAmount': 2, 'DebtInstrumentFaceAmount': 1}: unmatched -> unmatched
    - FINER.test.0043#1 [BAND] OperatingLeaseLiability -> DebtInstrumentCarryingAmount votes {'DebtInstrumentCarryingAmount': 2, 'DebtInstrumentFaceAmount': 1}: unmatched -> unmatched
    - FINER.test.0084#8 [BAND] RestructuringAndRelatedCostExpectedCost1 -> RestructuringCharges votes {'RestructuringCharges': 3}: incorrect -> correct
    - FINER.test.0084#9 [BAND] RestructuringAndRelatedCostExpectedCost1 -> RestructuringCharges votes {'RestructuringCharges': 3}: incorrect -> correct
    - FINER.test.0084#10 [BAND] RestructuringAndRelatedCostExpectedCost1 -> RestructuringCharges votes {'RestructuringCharges': 2, 'AccrualForEnvironmentalLossContingencies': 1}: incorrect -> correct
    - FINER.test.0098#1 [BAND] BusinessAcquisitionEquityInterestsIssuedOrIssuableNumberOfSharesIssued -> StockRepurchasedAndRetiredDuringPeriodShares votes {'AccrualForEnvironmentalLossContingencies': 1, 'StockRepurchasedAndRetiredDuringPeriodShares': 2}: unmatched -> unmatched
    - FINER.test.0098#2 [BAND] BusinessAcquisitionEquityInterestsIssuedOrIssuableNumberOfSharesIssued -> StockRepurchasedAndRetiredDuringPeriodShares votes {'StockRepurchasedAndRetiredDuringPeriodShares': 2, 'CashAndCashEquivalentsFairValueDisclosure': 1}: unmatched -> unmatched
    - FINER.test.0098#7 [BAND] CommonStockDividendsPerShareDeclared -> AccrualForEnvironmentalLossContingencies votes {'AccrualForEnvironmentalLossContingencies': 3}: unmatched -> unmatched
    - FINER.test.0098#9 [BAND] CommonStockDividendsPerShareDeclared -> AccrualForEnvironmentalLossContingencies votes {'AccrualForEnvironmentalLossContingencies': 3}: unmatched -> unmatched
    - FINER.test.0098#10 [BAND] CONCEPT_LESS -> AccrualForEnvironmentalLossContingencies votes {'AccrualForEnvironmentalLossContingencies': 2}: unmatched -> unmatched
    - FINER.test.0098#11 [BAND] CONCEPT_LESS -> AccrualForEnvironmentalLossContingencies votes {'AccrualForEnvironmentalLossContingencies': 3}: unmatched -> unmatched
    - FINER.test.0044#0 [BAND] NumberOfOperatingSegments -> AccrualForEnvironmentalLossContingencies votes {'AccrualForEnvironmentalLossContingencies': 2, 'NumberOfRealEstateProperties': 1}: unmatched -> unmatched
    - FINER.test.0080#8 [BAND] DebtInstrumentBasisSpreadOnVariableRate1 -> DebtInstrumentRedemptionPricePercentage votes {'DebtInstrumentRedemptionPricePercentage': 2, 'AccrualForEnvironmentalLossContingencies': 1}: incorrect -> correct
    - FINER.test.0080#10 [BAND] DebtInstrumentFairValue -> DebtInstrumentCarryingAmount votes {'DebtInstrumentCarryingAmount': 2, 'AccrualForEnvironmentalLossContingencies': 1}: unmatched -> unmatched
    - FINER.test.0037#1 [BAND] DebtInstrumentFairValue -> AccrualForEnvironmentalLossContingencies votes {'DebtInstrumentFairValue': 1, 'AccrualForEnvironmentalLossContingencies': 2}: unmatched -> unmatched
    - FINER.test.0037#3 [BAND] DebtInstrumentInterestRateEffectivePercentage -> DebtInstrumentInterestRateStatedPercentage votes {'DebtInstrumentInterestRateStatedPercentage': 2, 'AccrualForEnvironmentalLossContingencies': 1}: unmatched -> unmatched
    - FINER.test.0037#4 [BAND] DebtInstrumentInterestRateEffectivePercentage -> DebtInstrumentInterestRateStatedPercentage votes {'DebtInstrumentInterestRateStatedPercentage': 2, 'AccrualForEnvironmentalLossContingencies': 1}: incorrect -> incorrect
    - FINER.test.0037#5 [BAND] DebtInstrumentInterestRateEffectivePercentage -> DebtInstrumentInterestRateStatedPercentage votes {'DebtInstrumentInterestRateStatedPercentage': 2, 'AccrualForEnvironmentalLossContingencies': 1}: incorrect -> incorrect
    - FINER.test.0037#10 [BAND] DebtInstrumentInterestRateStatedPercentage -> DebtInstrumentInterestRateEffectivePercentage votes {'DebtInstrumentInterestRateEffectivePercentage': 2}: incorrect -> incorrect
    - FINER.test.0037#12 [BAND] CONCEPT_LESS -> AccrualForEnvironmentalLossContingencies votes {'CONCEPT_LESS': 1, 'AccrualForEnvironmentalLossContingencies': 2}: unmatched -> unmatched
    - FINER.test.0037#13 [BAND] CONCEPT_LESS -> AccrualForEnvironmentalLossContingencies votes {'CONCEPT_LESS': 1, 'AccrualForEnvironmentalLossContingencies': 2}: unmatched -> unmatched
    - FINER.test.0010#2 [BAND] DebtInstrumentCarryingAmount -> DebtInstrumentRedemptionPricePercentage votes {'DebtInstrumentRedemptionPricePercentage': 3}: unmatched -> unmatched
    - FINER.test.0024#4 [BAND] Revenues -> RevenueFromContractWithCustomerExcludingAssessedTax votes {'RevenueFromContractWithCustomerExcludingAssessedTax': 2, 'Revenues': 1}: incorrect -> incorrect
    - FINER.test.0024#7 [BAND] DebtInstrumentFaceAmount -> AccrualForEnvironmentalLossContingencies votes {'DebtInstrumentFaceAmount': 1, 'AccrualForEnvironmentalLossContingencies': 2}: incorrect -> incorrect
    - FINER.test.0024#12 [BAND] MinorityInterestOwnershipPercentageByNoncontrollingOwners -> DebtInstrumentInterestRateEffectivePercentage votes {'DebtInstrumentInterestRateEffectivePercentage': 2, 'EquityMethodInvestmentOwnershipPercentage': 1}: unmatched -> unmatched
    - FINER.test.0024#13 [BAND] MinorityInterestOwnershipPercentageByNoncontrollingOwners -> DebtInstrumentFaceAmount votes {'DebtInstrumentFaceAmount': 3}: unmatched -> unmatched
    - FINER.test.0050#0 [BAND] AreaOfRealEstateProperty -> OperatingLeaseWeightedAverageDiscountRatePercent votes {'AreaOfRealEstateProperty': 1, 'OperatingLeaseWeightedAverageDiscountRatePercent': 2}: incorrect -> incorrect
    - FINER.test.0104#0 [BAND] ContractWithCustomerLiability -> RevenueRemainingPerformanceObligation votes {'RevenueRemainingPerformanceObligation': 2, 'ContractWithCustomerLiability': 1}: unmatched -> unmatched
    - FINER.test.0104#1 [BAND] Revenues -> RevenueFromContractWithCustomerExcludingAssessedTax votes {'RevenueFromContractWithCustomerExcludingAssessedTax': 2, 'RevenueRemainingPerformanceObligation': 1}: unmatched -> unmatched
    - FINER.test.0104#2 [BAND] Revenues -> RevenueFromContractWithCustomerExcludingAssessedTax votes {'RevenueFromContractWithCustomerExcludingAssessedTax': 2, 'RevenueRemainingPerformanceObligation': 1}: incorrect -> incorrect
    - FINER.test.0104#3 [BAND] Revenues -> RevenueFromContractWithCustomerExcludingAssessedTax votes {'RevenueFromContractWithCustomerExcludingAssessedTax': 2, 'RevenueRemainingPerformanceObligation': 1}: incorrect -> incorrect
    - FINER.test.0104#6 [BAND] BusinessCombinationConsiderationTransferred1 -> BusinessCombinationAcquisitionRelatedCosts votes {'AccrualForEnvironmentalLossContingencies': 1, 'BusinessCombinationAcquisitionRelatedCosts': 2}: incorrect -> incorrect
    - FINER.test.0013#13 [BAND] InterestExpense -> InterestExpenseDebt votes {'InterestExpenseDebt': 3}: unmatched -> unmatched
    - FINER.test.0013#17 [BAND] InterestExpense -> InterestExpenseDebt votes {'InterestExpenseDebt': 2, 'AccrualForEnvironmentalLossContingencies': 1}: unmatched -> unmatched
    - FINER.test.0013#19 [BAND] InterestExpense -> AccrualForEnvironmentalLossContingencies votes {'AccrualForEnvironmentalLossContingencies': 2, 'DebtInstrumentUnamortizedDiscount': 1}: incorrect -> incorrect
    - FINER.test.0013#20 [BAND] DebtInstrumentInterestRateEffectivePercentage -> DebtWeightedAverageInterestRate votes {'DebtWeightedAverageInterestRate': 2, 'AccrualForEnvironmentalLossContingencies': 1}: correct -> incorrect
    - FINER.test.0013#21 [BAND] DebtInstrumentInterestRateEffectivePercentage -> DebtWeightedAverageInterestRate votes {'DebtWeightedAverageInterestRate': 2, 'DebtInstrumentInterestRateEffectivePercentage': 1}: correct -> incorrect
    - FINER.test.0013#24 [BAND] DeferredFinanceCostsGross -> DebtInstrumentUnamortizedDiscount votes {'DebtInstrumentUnamortizedDiscount': 2, 'DeferredFinanceCostsGross': 1}: unmatched -> unmatched
    - FINER.test.0013#25 [BAND] DeferredFinanceCostsGross -> DebtInstrumentUnamortizedDiscount votes {'DebtInstrumentUnamortizedDiscount': 2, 'DeferredFinanceCostsGross': 1}: unmatched -> unmatched
    - FINER.test.0052#0 [BAND] DebtInstrumentRedemptionPricePercentage -> LongTermDebt votes {'LongTermDebt': 3}: unmatched -> unmatched
    - FINER.test.0052#1 [BAND] DebtInstrumentRedemptionPricePercentage -> EmployeeServiceShareBasedCompensationNonvestedAwardsTotalCompensationCostNotYetRecognizedPeriodForRecognition1 votes {'EmployeeServiceShareBasedCompensationNonvestedAwardsTotalCompensationCostNotYetRecognizedPeriodForRecognition1': 3}: unmatched -> unmatched
    - FINER.test.0052#4 [BAND] DebtInstrumentRedemptionPricePercentage -> AccrualForEnvironmentalLossContingencies votes {'AccrualForEnvironmentalLossContingencies': 2, 'PublicUtilitiesRequestedRateIncreaseDecreaseAmount': 1}: unmatched -> unmatched
    - FINER.test.0052#7 [BAND] AccrualForEnvironmentalLossContingencies -> DebtInstrumentInterestRateStatedPercentage votes {'AccrualForEnvironmentalLossContingencies': 1, 'DebtInstrumentInterestRateStatedPercentage': 2}: incorrect -> incorrect
    - FINER.test.0052#16 [BAND] DebtWeightedAverageInterestRate -> AccrualForEnvironmentalLossContingencies votes {'AccrualForEnvironmentalLossContingencies': 2, 'CONCEPT_LESS': 1}: unmatched -> unmatched
    - FINER.test.0052#19 [BAND] DebtWeightedAverageInterestRate -> DebtInstrumentInterestRateEffectivePercentage votes {'DebtInstrumentInterestRateEffectivePercentage': 2, 'DebtInstrumentInterestRateStatedPercentage': 1}: incorrect -> incorrect
    - FINER.test.0052#26 [BAND] AccrualForEnvironmentalLossContingencies -> LossContingencyDamagesSoughtValue votes {'LossContingencyDamagesSoughtValue': 2, 'AccrualForEnvironmentalLossContingencies': 1}: unmatched -> unmatched
    - FINER.test.0021#0 [BAND] PreferredStockDividendRatePercentage -> AccrualForEnvironmentalLossContingencies votes {'AccrualForEnvironmentalLossContingencies': 2, 'PreferredStockDividendRatePercentage': 1}: unmatched -> unmatched
    - FINER.test.0021#1 [BAND] PreferredStockDividendRatePercentage -> AccrualForEnvironmentalLossContingencies votes {'AccrualForEnvironmentalLossContingencies': 2, 'PreferredStockDividendRatePercentage': 1}: unmatched -> unmatched
    - FINER.test.0021#2 [BAND] PreferredStockDividendRatePercentage -> AccrualForEnvironmentalLossContingencies votes {'AccrualForEnvironmentalLossContingencies': 2, 'PreferredStockDividendRatePercentage': 1}: unmatched -> unmatched
- rerun-finer-d2: by lane {'BAND': {'split': 44, 'tie': 60, 'changed': 94, 'single_sample': 10, 'unanimous': 83, 'not_resampled': 10}, 'REJECT': {'not_resampled': 3}}; changed 94, correct destroyed 5, gained 13, net +8; not_resampled had been {'unmatched': 12, 'correct': 1}
    - FINER.test.0103#0 [BAND] RevenueFromContractWithCustomerExcludingAssessedTax -> Revenues votes {'Revenues': 3}: incorrect -> incorrect
    - FINER.test.0103#1 [BAND] RevenueFromContractWithCustomerExcludingAssessedTax -> Revenues votes {'Revenues': 3}: incorrect -> incorrect
    - FINER.test.0103#2 [BAND] RevenueFromContractWithCustomerExcludingAssessedTax -> Revenues votes {'Revenues': 3}: unmatched -> unmatched
    - FINER.test.0103#3 [BAND] RevenueFromContractWithCustomerExcludingAssessedTax -> Revenues votes {'Revenues': 2, 'AccrualForEnvironmentalLossContingencies': 1}: unmatched -> unmatched
    - FINER.test.0003#14 [BAND] AntidilutiveSecuritiesExcludedFromComputationOfEarningsPerShareAmount -> AccrualForEnvironmentalLossContingencies votes {'AccrualForEnvironmentalLossContingencies': 3}: unmatched -> unmatched
    - FINER.test.0003#15 [BAND] CashAndCashEquivalentsFairValueDisclosure -> AccrualForEnvironmentalLossContingencies votes {'AccrualForEnvironmentalLossContingencies': 2, 'ConcentrationRiskPercentage1': 1}: incorrect -> incorrect
    - FINER.test.0003#17 [BAND] CommonStockCapitalSharesReservedForFutureIssuance -> AccrualForEnvironmentalLossContingencies votes {'AccrualForEnvironmentalLossContingencies': 3}: unmatched -> unmatched
    - FINER.test.0059#11 [BAND] Depreciation -> AmortizationOfIntangibleAssets votes {'AmortizationOfIntangibleAssets': 3}: incorrect -> correct
    - FINER.test.0059#12 [BAND] Depreciation -> AmortizationOfIntangibleAssets votes {'AmortizationOfIntangibleAssets': 3}: incorrect -> correct
    - FINER.test.0073#0 [BAND] AccrualForEnvironmentalLossContingencies -> CommonStockSharesOutstanding votes {'CommonStockSharesOutstanding': 3}: unmatched -> unmatched
    - FINER.test.0073#1 [BAND] AccrualForEnvironmentalLossContingencies -> SharePrice votes {'SharePrice': 2, 'ClassOfWarrantOrRightExercisePriceOfWarrantsOrRights1': 1}: unmatched -> unmatched
    - FINER.test.0025#0 [BAND] DebtInstrumentInterestRateStatedPercentage -> DebtInstrumentInterestRateEffectivePercentage votes {'DebtInstrumentInterestRateEffectivePercentage': 3}: unmatched -> unmatched
    - FINER.test.0025#1 [BAND] DebtInstrumentInterestRateStatedPercentage -> DebtInstrumentInterestRateEffectivePercentage votes {'DebtInstrumentInterestRateEffectivePercentage': 3}: unmatched -> unmatched
    - FINER.test.0047#0 [BAND] AccrualForEnvironmentalLossContingencies -> DebtInstrumentCarryingAmount votes {'DebtInstrumentCarryingAmount': 2, 'AccrualForEnvironmentalLossContingencies': 1}: unmatched -> unmatched
    - FINER.test.0047#1 [BAND] MinorityInterestOwnershipPercentageByNoncontrollingOwners -> BusinessAcquisitionEquityInterestsIssuedOrIssuableNumberOfSharesIssued votes {'BusinessAcquisitionEquityInterestsIssuedOrIssuableNumberOfSharesIssued': 3}: unmatched -> unmatched
    - FINER.test.0047#2 [BAND] MinorityInterestOwnershipPercentageByNoncontrollingOwners -> BusinessAcquisitionPercentageOfVotingInterestsAcquired votes {'BusinessAcquisitionPercentageOfVotingInterestsAcquired': 3}: correct -> incorrect
    - FINER.test.0047#3 [BAND] MinorityInterestOwnershipPercentageByNoncontrollingOwners -> BusinessAcquisitionPercentageOfVotingInterestsAcquired votes {'BusinessAcquisitionPercentageOfVotingInterestsAcquired': 3}: incorrect -> incorrect
    - FINER.test.0047#6 [BAND] AccrualForEnvironmentalLossContingencies -> EffectiveIncomeTaxRateContinuingOperations votes {'EffectiveIncomeTaxRateContinuingOperations': 2, 'AccrualForEnvironmentalLossContingencies': 1}: incorrect -> correct
    - FINER.test.0047#9 [BAND] IncomeLossFromEquityMethodInvestments -> CONCEPT_LESS votes {'EffectiveIncomeTaxRateContinuingOperations': 1, 'CONCEPT_LESS': 2}: unmatched -> unmatched
    - FINER.test.0069#0 [BAND] DebtInstrumentFaceAmount -> AccrualForEnvironmentalLossContingencies votes {'AccrualForEnvironmentalLossContingencies': 3}: unmatched -> unmatched
    - FINER.test.0023#1 [BAND] BusinessAcquisitionPercentageOfVotingInterestsAcquired -> ConcentrationRiskPercentage1 votes {'ConcentrationRiskPercentage1': 3}: unmatched -> unmatched
    - FINER.test.0023#3 [BAND] BusinessAcquisitionPercentageOfVotingInterestsAcquired -> ConcentrationRiskPercentage1 votes {'ConcentrationRiskPercentage1': 3}: unmatched -> unmatched
    - FINER.test.0023#5 [BAND] BusinessAcquisitionPercentageOfVotingInterestsAcquired -> ConcentrationRiskPercentage1 votes {'ConcentrationRiskPercentage1': 3}: unmatched -> unmatched
    - FINER.test.0016#0 [BAND] AccrualForEnvironmentalLossContingencies -> DebtInstrumentCarryingAmount votes {'DebtInstrumentCarryingAmount': 2, 'CashAndCashEquivalentsFairValueDisclosure': 1}: unmatched -> unmatched
    - FINER.test.0016#1 [BAND] AccrualForEnvironmentalLossContingencies -> DebtInstrumentInterestRateEffectivePercentage votes {'DebtInstrumentInterestRateEffectivePercentage': 2, 'DebtWeightedAverageInterestRate': 1}: unmatched -> unmatched
    - FINER.test.0016#2 [BAND] AccrualForEnvironmentalLossContingencies -> DebtInstrumentInterestRateEffectivePercentage votes {'DebtInstrumentInterestRateEffectivePercentage': 2, 'DebtWeightedAverageInterestRate': 1}: unmatched -> unmatched
    - FINER.test.0016#3 [BAND] AccrualForEnvironmentalLossContingencies -> DebtInstrumentInterestRateEffectivePercentage votes {'DebtInstrumentInterestRateEffectivePercentage': 2, 'DebtWeightedAverageInterestRate': 1}: unmatched -> unmatched
    - FINER.test.0016#5 [BAND] DebtInstrumentFaceAmount -> DebtInstrumentCarryingAmount votes {'DebtInstrumentCarryingAmount': 2, 'CashAndCashEquivalentsFairValueDisclosure': 1}: unmatched -> unmatched
    - FINER.test.0085#4 [BAND] AccrualForEnvironmentalLossContingencies -> InterestExpense votes {'InterestExpense': 3}: incorrect -> correct
    - FINER.test.0076#0 [BAND] CONCEPT_LESS -> AccrualForEnvironmentalLossContingencies votes {'AccrualForEnvironmentalLossContingencies': 2, 'CommonStockSharesOutstanding': 1}: unmatched -> unmatched
    - FINER.test.0008#0 [BAND] LineOfCredit -> DebtInstrumentCarryingAmount votes {'DebtInstrumentCarryingAmount': 2, 'AccrualForEnvironmentalLossContingencies': 1}: unmatched -> unmatched
    - FINER.test.0008#1 [BAND] LineOfCredit -> DebtInstrumentCarryingAmount votes {'DebtInstrumentCarryingAmount': 2, 'LineOfCreditFacilityMaximumBorrowingCapacity': 1}: unmatched -> unmatched
    - FINER.test.0008#4 [BAND] LineOfCredit -> DebtInstrumentCarryingAmount votes {'DebtInstrumentCarryingAmount': 2, 'LongTermDebt': 1}: unmatched -> unmatched
    - FINER.test.0107#1 [BAND] AccrualForEnvironmentalLossContingencies -> ConcentrationRiskPercentage1 votes {'ConcentrationRiskPercentage1': 2}: unmatched -> unmatched
    - FINER.test.0043#0 [BAND] OperatingLeaseLiability -> DebtInstrumentCarryingAmount votes {'DebtInstrumentCarryingAmount': 2, 'OperatingLeaseCost': 1}: unmatched -> unmatched
    - FINER.test.0043#1 [BAND] OperatingLeaseLiability -> DebtInstrumentCarryingAmount votes {'DebtInstrumentCarryingAmount': 2, 'OperatingLeaseCost': 1}: unmatched -> unmatched
    - FINER.test.0084#6 [BAND] AccrualForEnvironmentalLossContingencies -> RestructuringCharges votes {'RestructuringCharges': 2, 'RestructuringAndRelatedCostExpectedCost1': 1}: unmatched -> unmatched
    - FINER.test.0084#7 [BAND] RestructuringAndRelatedCostExpectedCost1 -> DebtInstrumentBasisSpreadOnVariableRate1 votes {'DebtInstrumentBasisSpreadOnVariableRate1': 2, 'AccrualForEnvironmentalLossContingencies': 1}: unmatched -> unmatched
    - FINER.test.0084#8 [BAND] RestructuringAndRelatedCostExpectedCost1 -> RestructuringCharges votes {'RestructuringCharges': 2, 'RestructuringAndRelatedCostExpectedCost1': 1}: incorrect -> correct
    - FINER.test.0084#9 [BAND] RestructuringAndRelatedCostExpectedCost1 -> RestructuringCharges votes {'RestructuringCharges': 2, 'RestructuringAndRelatedCostExpectedCost1': 1}: incorrect -> correct
    - FINER.test.0084#10 [BAND] RestructuringAndRelatedCostExpectedCost1 -> RestructuringCharges votes {'RestructuringCharges': 2, 'RestructuringAndRelatedCostExpectedCost1': 1}: incorrect -> correct
    - FINER.test.0098#0 [BAND] DebtInstrumentFaceAmount -> StockRepurchaseProgramAuthorizedAmount1 votes {'DebtInstrumentMaturityDate': 1, 'StockRepurchaseProgramAuthorizedAmount1': 2}: incorrect -> correct
    - FINER.test.0098#1 [BAND] BusinessAcquisitionEquityInterestsIssuedOrIssuableNumberOfSharesIssued -> StockRepurchasedAndRetiredDuringPeriodShares votes {'CommonStockSharesOutstanding': 1, 'StockRepurchasedAndRetiredDuringPeriodShares': 2}: unmatched -> unmatched
    - FINER.test.0098#4 [BAND] DebtInstrumentFaceAmount -> StockRepurchaseProgramAuthorizedAmount1 votes {'AccrualForEnvironmentalLossContingencies': 1, 'StockRepurchaseProgramAuthorizedAmount1': 2}: incorrect -> correct
    - FINER.test.0098#10 [BAND] CONCEPT_LESS -> AccrualForEnvironmentalLossContingencies votes {'AccrualForEnvironmentalLossContingencies': 3}: unmatched -> unmatched
    - FINER.test.0098#11 [BAND] CONCEPT_LESS -> AccrualForEnvironmentalLossContingencies votes {'AccrualForEnvironmentalLossContingencies': 3}: unmatched -> unmatched
    - FINER.test.0044#0 [BAND] NumberOfOperatingSegments -> NumberOfRealEstateProperties votes {'NumberOfRealEstateProperties': 2, 'BusinessAcquisitionEquityInterestsIssuedOrIssuableNumberOfSharesIssued': 1}: unmatched -> unmatched
    - FINER.test.0044#1 [BAND] SaleOfStockNumberOfSharesIssuedInTransaction -> CommonStockSharesOutstanding votes {'CommonStockSharesOutstanding': 2, 'BusinessAcquisitionEquityInterestsIssuedOrIssuableNumberOfSharesIssued': 1}: unmatched -> unmatched
    - FINER.test.0044#2 [BAND] SaleOfStockNumberOfSharesIssuedInTransaction -> CommonStockSharesOutstanding votes {'CommonStockSharesOutstanding': 2, 'BusinessAcquisitionEquityInterestsIssuedOrIssuableNumberOfSharesIssued': 1}: unmatched -> unmatched
    - FINER.test.0044#6 [BAND] ConcentrationRiskPercentage1 -> MinorityInterestOwnershipPercentageByNoncontrollingOwners votes {'AccrualForEnvironmentalLossContingencies': 1, 'MinorityInterestOwnershipPercentageByNoncontrollingOwners': 2}: unmatched -> unmatched
    - FINER.test.0044#7 [BAND] ConcentrationRiskPercentage1 -> AccrualForEnvironmentalLossContingencies votes {'AccrualForEnvironmentalLossContingencies': 2, 'DebtInstrumentFaceAmount': 1}: unmatched -> unmatched
    - FINER.test.0044#8 [BAND] ConcentrationRiskPercentage1 -> MinorityInterestOwnershipPercentageByNoncontrollingOwners votes {'AccrualForEnvironmentalLossContingencies': 1, 'MinorityInterestOwnershipPercentageByNoncontrollingOwners': 2}: incorrect -> incorrect
    - FINER.test.0046#2 [BAND] LeaseAndRentalExpense -> AllocatedShareBasedCompensationExpense votes {'AllocatedShareBasedCompensationExpense': 2, 'AccrualForEnvironmentalLossContingencies': 1}: incorrect -> incorrect
    - FINER.test.0046#3 [BAND] LeaseAndRentalExpense -> AllocatedShareBasedCompensationExpense votes {'AllocatedShareBasedCompensationExpense': 2, 'AccrualForEnvironmentalLossContingencies': 1}: incorrect -> incorrect
    - FINER.test.0046#10 [BAND] AllocatedShareBasedCompensationExpense -> ShareBasedCompensation votes {'ShareBasedCompensation': 3}: incorrect -> incorrect
    - FINER.test.0046#11 [BAND] AllocatedShareBasedCompensationExpense -> ShareBasedCompensation votes {'ShareBasedCompensation': 3}: incorrect -> incorrect
    - FINER.test.0046#12 [BAND] AccrualForEnvironmentalLossContingencies -> CONCEPT_LESS votes {'CONCEPT_LESS': 2, 'AccrualForEnvironmentalLossContingencies': 1}: unmatched -> unmatched
    - FINER.test.0080#10 [BAND] DebtInstrumentFairValue -> DebtInstrumentCarryingAmount votes {'DebtInstrumentCarryingAmount': 3}: unmatched -> unmatched
    - FINER.test.0037#4 [BAND] DebtInstrumentInterestRateEffectivePercentage -> DebtInstrumentInterestRateStatedPercentage votes {'DebtInstrumentInterestRateStatedPercentage': 2, 'DebtInstrumentInterestRateEffectivePercentage': 1}: incorrect -> incorrect
    - FINER.test.0037#5 [BAND] DebtInstrumentInterestRateEffectivePercentage -> DebtInstrumentInterestRateStatedPercentage votes {'DebtInstrumentInterestRateStatedPercentage': 2, 'DebtInstrumentInterestRateEffectivePercentage': 1}: incorrect -> incorrect
    - FINER.test.0037#8 [BAND] DerivativeNotionalAmount -> AccrualForEnvironmentalLossContingencies votes {'AccrualForEnvironmentalLossContingencies': 2, 'CONCEPT_LESS': 1}: correct -> incorrect
    - FINER.test.0037#10 [BAND] DebtInstrumentInterestRateStatedPercentage -> DebtInstrumentInterestRateEffectivePercentage votes {'DebtInstrumentInterestRateEffectivePercentage': 2, 'DebtInstrumentInterestRateStatedPercentage': 1}: incorrect -> incorrect
    - FINER.test.0037#16 [BAND] AccrualForEnvironmentalLossContingencies -> DebtInstrumentInterestRateEffectivePercentage votes {'DebtInstrumentInterestRateEffectivePercentage': 2, 'AccrualForEnvironmentalLossContingencies': 1}: unmatched -> unmatched
    - FINER.test.0010#2 [BAND] DebtInstrumentCarryingAmount -> DebtInstrumentRedemptionPricePercentage votes {'DebtInstrumentRedemptionPricePercentage': 3}: unmatched -> unmatched
    - FINER.test.0010#7 [BAND] DeferredFinanceCostsGross -> DeferredFinanceCostsNet votes {'DeferredFinanceCostsNet': 2, 'DeferredFinanceCostsGross': 1}: incorrect -> correct
    - FINER.test.0010#10 [BAND] DebtInstrumentInterestRateStatedPercentage -> DebtInstrumentInterestRateEffectivePercentage votes {'DebtInstrumentInterestRateEffectivePercentage': 3}: correct -> incorrect
    - FINER.test.0024#4 [BAND] Revenues -> AccrualForEnvironmentalLossContingencies votes {'AccrualForEnvironmentalLossContingencies': 3}: incorrect -> incorrect
    - FINER.test.0024#10 [BAND] MinorityInterestOwnershipPercentageByNoncontrollingOwners -> ConcentrationRiskPercentage1 votes {'BusinessAcquisitionPercentageOfVotingInterestsAcquired': 1, 'ConcentrationRiskPercentage1': 2}: unmatched -> unmatched
    - FINER.test.0048#1 [BAND] SaleOfStockNumberOfSharesIssuedInTransaction -> AccrualForEnvironmentalLossContingencies votes {'AccrualForEnvironmentalLossContingencies': 2, 'CommonStockSharesOutstanding': 1}: unmatched -> unmatched
    - FINER.test.0104#0 [BAND] ContractWithCustomerLiability -> RevenueRemainingPerformanceObligation votes {'RevenueRemainingPerformanceObligation': 2, 'ContractWithCustomerLiability': 1}: unmatched -> unmatched
    - FINER.test.0104#1 [BAND] Revenues -> RevenueRemainingPerformanceObligation votes {'RevenueFromContractWithCustomerExcludingAssessedTax': 1, 'RevenueRemainingPerformanceObligation': 2}: unmatched -> unmatched
    - FINER.test.0104#2 [BAND] Revenues -> RevenueRemainingPerformanceObligation votes {'RevenueFromContractWithCustomerExcludingAssessedTax': 1, 'RevenueRemainingPerformanceObligation': 2}: incorrect -> correct
    - FINER.test.0104#3 [BAND] Revenues -> RevenueRemainingPerformanceObligation votes {'RevenueFromContractWithCustomerExcludingAssessedTax': 1, 'RevenueRemainingPerformanceObligation': 2}: incorrect -> correct
    - FINER.test.0104#6 [BAND] BusinessCombinationConsiderationTransferred1 -> PaymentsToAcquireBusinessesGross votes {'PaymentsToAcquireBusinessesGross': 2, 'BusinessCombinationConsiderationTransferred1': 1}: incorrect -> correct
    - FINER.test.0104#8 [BAND] BusinessCombinationConsiderationTransferred1 -> PaymentsToAcquireBusinessesGross votes {'PaymentsToAcquireBusinessesGross': 2, 'BusinessCombinationConsiderationTransferred1': 1}: correct -> incorrect
    - FINER.test.0104#9 [BAND] BusinessCombinationConsiderationTransferred1 -> AccrualForEnvironmentalLossContingencies votes {'AccrualForEnvironmentalLossContingencies': 2, 'BusinessCombinationConsiderationTransferred1': 1}: unmatched -> unmatched
    - FINER.test.0093#8 [BAND] AccrualForEnvironmentalLossContingencies -> LineOfCredit votes {'InterestExpense': 1, 'LineOfCredit': 2}: incorrect -> incorrect
    - FINER.test.0013#2 [BAND] DebtInstrumentInterestRateStatedPercentage -> AccrualForEnvironmentalLossContingencies votes {'AccrualForEnvironmentalLossContingencies': 2, 'DebtInstrumentInterestRateStatedPercentage': 1}: correct -> incorrect
    - FINER.test.0013#3 [BAND] AccrualForEnvironmentalLossContingencies -> DebtInstrumentConvertibleConversionPrice1 votes {'DebtInstrumentConvertibleConversionPrice1': 2, 'AccrualForEnvironmentalLossContingencies': 1}: unmatched -> unmatched
    - FINER.test.0013#4 [BAND] AccrualForEnvironmentalLossContingencies -> DebtInstrumentConvertibleConversionPrice1 votes {'DebtInstrumentConvertibleConversionPrice1': 2, 'AccrualForEnvironmentalLossContingencies': 1}: unmatched -> unmatched
    - FINER.test.0013#5 [BAND] AccrualForEnvironmentalLossContingencies -> DebtInstrumentConvertibleConversionPrice1 votes {'DebtInstrumentConvertibleConversionPrice1': 2, 'AccrualForEnvironmentalLossContingencies': 1}: unmatched -> unmatched
    - FINER.test.0013#19 [BAND] InterestExpense -> DeferredFinanceCostsGross votes {'DeferredFinanceCostsGross': 2, 'DebtInstrumentUnamortizedDiscount': 1}: incorrect -> incorrect
    - FINER.test.0013#24 [BAND] DeferredFinanceCostsGross -> DebtInstrumentUnamortizedDiscount votes {'DebtInstrumentUnamortizedDiscount': 3}: unmatched -> unmatched
    - FINER.test.0013#25 [BAND] DeferredFinanceCostsGross -> DebtInstrumentUnamortizedDiscount votes {'DebtInstrumentUnamortizedDiscount': 3}: unmatched -> unmatched
    - FINER.test.0052#0 [BAND] DebtInstrumentRedemptionPricePercentage -> ConcentrationRiskPercentage1 votes {'ConcentrationRiskPercentage1': 2, 'LongTermDebt': 1}: unmatched -> unmatched
    - FINER.test.0052#1 [BAND] DebtInstrumentRedemptionPricePercentage -> ConcentrationRiskPercentage1 votes {'ConcentrationRiskPercentage1': 2, 'EmployeeServiceShareBasedCompensationNonvestedAwardsTotalCompensationCostNotYetRecognizedPeriodForRecognition1': 1}: unmatched -> unmatched
    - FINER.test.0052#4 [BAND] DebtInstrumentRedemptionPricePercentage -> ConcentrationRiskPercentage1 votes {'ConcentrationRiskPercentage1': 2, 'AccrualForEnvironmentalLossContingencies': 1}: unmatched -> unmatched
    - FINER.test.0052#7 [BAND] AccrualForEnvironmentalLossContingencies -> DebtInstrumentInterestRateEffectivePercentage votes {'DebtInstrumentInterestRateEffectivePercentage': 2, 'DebtInstrumentInterestRateStatedPercentage': 1}: incorrect -> incorrect
    - FINER.test.0052#16 [BAND] DebtWeightedAverageInterestRate -> DebtInstrumentInterestRateEffectivePercentage votes {'AccrualForEnvironmentalLossContingencies': 1, 'DebtInstrumentInterestRateEffectivePercentage': 2}: unmatched -> unmatched
    - FINER.test.0052#19 [BAND] DebtWeightedAverageInterestRate -> DebtInstrumentInterestRateEffectivePercentage votes {'AccrualForEnvironmentalLossContingencies': 1, 'DebtInstrumentInterestRateEffectivePercentage': 2}: incorrect -> incorrect
    - FINER.test.0052#26 [BAND] AccrualForEnvironmentalLossContingencies -> DebtInstrumentFaceAmount votes {'AccrualForEnvironmentalLossContingencies': 1, 'DebtInstrumentFaceAmount': 2}: unmatched -> unmatched
    - FINER.test.0021#0 [BAND] PreferredStockDividendRatePercentage -> AccrualForEnvironmentalLossContingencies votes {'AccrualForEnvironmentalLossContingencies': 3}: unmatched -> unmatched
    - FINER.test.0021#1 [BAND] PreferredStockDividendRatePercentage -> AccrualForEnvironmentalLossContingencies votes {'AccrualForEnvironmentalLossContingencies': 3}: unmatched -> unmatched
    - FINER.test.0021#2 [BAND] PreferredStockDividendRatePercentage -> AccrualForEnvironmentalLossContingencies votes {'AccrualForEnvironmentalLossContingencies': 3}: unmatched -> unmatched

## Rung 4 (blind, shipped) vs the menu arms
| draw | arm | judged | pass | fail | P(correct|pass) | P(correct|fail) | separation | span_bad | code_bad | menu shown | not-on-list | best correct | best = pick |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| rerun-finer-d0 | base | 296 | 45 | 251 | 0.444 | 0.124 | 3.60x | 149 | 243 | 0 | 0 | 0 | 0 |
| rerun-finer-d0 | judgemenu | 302 | 190 | 112 | 0.268 | 0.009 | 30.06x | 56 | 100 | 302 | 105 | 26 | 115 |
| rerun-finer-d0 | judgeshuffle | 301 | 186 | 115 | 0.274 | 0.009 | 31.53x | 50 | 105 | 301 | 109 | 33 | 119 |
| rerun-finer-d1 | base | 296 | 47 | 249 | 0.404 | 0.137 | 2.96x | 149 | 241 | 0 | 0 | 0 | 0 |
| rerun-finer-d1 | judgemenu | 302 | 192 | 110 | 0.276 | 0.009 | 30.36x | 55 | 95 | 302 | 100 | 26 | 117 |
| rerun-finer-d1 | judgeshuffle | 301 | 183 | 118 | 0.284 | 0.017 | 16.77x | 54 | 104 | 301 | 111 | 32 | 118 |
| rerun-finer-d2 | base | 295 | 46 | 249 | 0.370 | 0.145 | 2.56x | 142 | 243 | 0 | 0 | 0 | 0 |
| rerun-finer-d2 | judgemenu | 303 | 204 | 99 | 0.260 | 0.010 | 25.72x | 55 | 89 | 303 | 94 | 27 | 120 |
| rerun-finer-d2 | judgeshuffle | 301 | 195 | 106 | 0.272 | 0.009 | 28.81x | 50 | 95 | 301 | 99 | 32 | 128 |

## The shipped result and the policy arms (final state rows)
| draw | arm | n | ships | coverage | accuracy | **yield** | errors | err/100 | to a person | stack F1 exact | overlap |
|---|---|---|---|---|---|---|---|---|---|---|---|
| rerun-finer-d0 | base | 304 | 0 | 0.000 | 0.000 | **0.000** | 0 | 0.0 | 304 | 0.000 | 0.000 |
| rerun-finer-d0 | judgemenu | 304 | 0 | 0.000 | 0.000 | **0.000** | 0 | 0.0 | 304 | 0.000 | 0.000 |
| rerun-finer-d0 | judgeshuffle | 304 | 0 | 0.000 | 0.000 | **0.000** | 0 | 0.0 | 304 | 0.000 | 0.000 |
| rerun-finer-d0 | spine | 304 | 0 | 0.000 | 0.000 | **0.000** | 0 | 0.0 | 304 | 0.000 | 0.000 |
| rerun-finer-d1 | base | 304 | 0 | 0.000 | 0.000 | **0.000** | 0 | 0.0 | 304 | 0.000 | 0.000 |
| rerun-finer-d1 | judgemenu | 304 | 0 | 0.000 | 0.000 | **0.000** | 0 | 0.0 | 304 | 0.000 | 0.000 |
| rerun-finer-d1 | judgeshuffle | 304 | 0 | 0.000 | 0.000 | **0.000** | 0 | 0.0 | 304 | 0.000 | 0.000 |
| rerun-finer-d1 | spine | 304 | 0 | 0.000 | 0.000 | **0.000** | 0 | 0.0 | 304 | 0.000 | 0.000 |
| rerun-finer-d2 | base | 304 | 0 | 0.000 | 0.000 | **0.000** | 0 | 0.0 | 304 | 0.000 | 0.000 |
| rerun-finer-d2 | judgemenu | 304 | 0 | 0.000 | 0.000 | **0.000** | 0 | 0.0 | 304 | 0.000 | 0.000 |
| rerun-finer-d2 | judgeshuffle | 304 | 0 | 0.000 | 0.000 | **0.000** | 0 | 0.0 | 304 | 0.000 | 0.000 |
| rerun-finer-d2 | spine | 304 | 0 | 0.000 | 0.000 | **0.000** | 0 | 0.0 | 304 | 0.000 | 0.000 |

## Every rung's verdict as a shipping rule (one denominator: all records; F1 span-exact over what ships)
| draw | ship only when… | reads rung | ships | right code, exact span | exact span, wrong code | right code, boundary off | neither | to a person | of them right | accuracy | **yield** | F1 | extra tokens |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| rerun-finer-d0 | everything | 0 | 304 | 46 | 72 | 3 | 183 | 0 | 0 | 0.151 | **0.151** | 0.196 | 0 |
| rerun-finer-d0 | everything_after_r3 | 3 | 304 | 52 | 66 | 3 | 183 | 0 | 0 | 0.171 | **0.171** | 0.222 | 2,631,243 |
| rerun-finer-d0 | accept | 4 | 0 | 0 | 0 | 0 | 0 | 304 | 52 | 0.000 | **0.000** | 0.000 | 0 |
| rerun-finer-d0 | r3_unanimous | 3 | 97 | 24 | 16 | 2 | 55 | 207 | 28 | 0.247 | **0.079** | 0.183 | 2,631,243 |
| rerun-finer-d0 | r3_two_agree | 3 | 214 | 44 | 43 | 3 | 124 | 90 | 8 | 0.206 | **0.145** | 0.232 | 2,631,243 |
| rerun-finer-d0 | r4_blind_pass | 4 | 45 | 20 | 9 | 2 | 14 | 259 | 32 | 0.444 | **0.066** | 0.191 | 269,910 |
| rerun-finer-d0 | r4_menu_pass | 4 | 190 | 51 | 43 | 3 | 93 | 114 | 1 | 0.268 | **0.168** | 0.287 | 269,910 |
| rerun-finer-d1 | everything | 0 | 304 | 46 | 72 | 3 | 183 | 0 | 0 | 0.151 | **0.151** | 0.196 | 0 |
| rerun-finer-d1 | everything_after_r3 | 3 | 304 | 54 | 64 | 5 | 181 | 0 | 0 | 0.178 | **0.178** | 0.230 | 2,613,262 |
| rerun-finer-d1 | accept | 4 | 0 | 0 | 0 | 0 | 0 | 304 | 54 | 0.000 | **0.000** | 0.000 | 0 |
| rerun-finer-d1 | r3_unanimous | 3 | 68 | 23 | 9 | 0 | 36 | 236 | 31 | 0.338 | **0.076** | 0.197 | 2,613,262 |
| rerun-finer-d1 | r3_two_agree | 3 | 194 | 47 | 32 | 5 | 110 | 110 | 7 | 0.242 | **0.155** | 0.262 | 2,613,262 |
| rerun-finer-d1 | r4_blind_pass | 4 | 47 | 19 | 11 | 3 | 14 | 257 | 35 | 0.404 | **0.062** | 0.179 | 269,887 |
| rerun-finer-d1 | r4_menu_pass | 4 | 192 | 53 | 43 | 5 | 91 | 112 | 1 | 0.276 | **0.174** | 0.297 | 269,887 |
| rerun-finer-d2 | everything | 0 | 304 | 46 | 72 | 3 | 183 | 0 | 0 | 0.151 | **0.151** | 0.196 | 0 |
| rerun-finer-d2 | everything_after_r3 | 3 | 304 | 54 | 64 | 5 | 181 | 0 | 0 | 0.178 | **0.178** | 0.230 | 2,604,531 |
| rerun-finer-d2 | accept | 4 | 0 | 0 | 0 | 0 | 0 | 304 | 54 | 0.000 | **0.000** | 0.000 | 0 |
| rerun-finer-d2 | r3_unanimous | 3 | 101 | 33 | 14 | 0 | 54 | 203 | 21 | 0.327 | **0.109** | 0.248 | 2,604,531 |
| rerun-finer-d2 | r3_two_agree | 3 | 213 | 51 | 39 | 4 | 119 | 91 | 3 | 0.239 | **0.168** | 0.270 | 2,604,531 |
| rerun-finer-d2 | r4_blind_pass | 4 | 46 | 17 | 10 | 2 | 17 | 258 | 37 | 0.370 | **0.056** | 0.161 | 269,818 |
| rerun-finer-d2 | r4_menu_pass | 4 | 204 | 53 | 40 | 5 | 106 | 100 | 1 | 0.260 | **0.174** | 0.287 | 269,818 |
| mean of 3 | everything | 0 | 304.0 | | | | | 0.0 | 0.0 | 0.151 | **0.151** | 0.196 | 0 |
| mean of 3 | everything_after_r3 | 3 | 304.0 | | | | | 0.0 | 0.0 | 0.175 | **0.175** | 0.227 | 2,616,345 |
| mean of 3 | accept | 4 | 0.0 | | | | | 304.0 | 53.3 | 0.000 | **0.000** | 0.000 | 0 |
| mean of 3 | r3_unanimous | 3 | 88.7 | | | | | 215.3 | 26.7 | 0.304 | **0.088** | 0.210 | 2,616,345 |
| mean of 3 | r3_two_agree | 3 | 207.0 | | | | | 97.0 | 6.0 | 0.229 | **0.156** | 0.255 | 2,616,345 |
| mean of 3 | r4_blind_pass | 4 | 46.0 | | | | | 258.0 | 34.7 | 0.406 | **0.061** | 0.177 | 269,872 |
| mean of 3 | r4_menu_pass | 4 | 195.3 | | | | | 108.7 | 1.0 | 0.268 | **0.172** | 0.290 | 269,872 |

## Cost per rung, base draws (tokens / calls / p95 s / human minutes / records routed)
- rerun-finer-d0: r0: 947,360 / 110 / 135.1 / 0.0 / 0; r1: 0 / 0 / 0.0 / 0.0 / 0; r2: 0 / 0 / 0.0 / 0.0 / 0; r3: 2,631,243 / 303 / 295.65 / 0.0 / 0; r4: 269,910 / 304 / 2.31 / 0.0 / 0; r5: 0 / 0 / 0.0 / 0.0 / 0; r6: 0 / 0 / 0.0 / 608.0 / 304
- rerun-finer-d1: r0: 947,360 / 110 / 139.72 / 0.0 / 0; r1: 0 / 0 / 0.0 / 0.0 / 0; r2: 0 / 0 / 0.0 / 0.0 / 0; r3: 2,613,262 / 299 / 356.45 / 0.0 / 0; r4: 269,887 / 304 / 2.31 / 0.0 / 0; r5: 0 / 0 / 0.0 / 0.0 / 0; r6: 0 / 0 / 0.0 / 608.0 / 304
- rerun-finer-d2: r0: 947,360 / 110 / 143.04 / 0.0 / 0; r1: 0 / 0 / 0.0 / 0.0 / 0; r2: 0 / 0 / 0.0 / 0.0 / 0; r3: 2,604,531 / 301 / 319.25 / 0.0 / 0; r4: 269,818 / 304 / 2.45 / 0.0 / 0; r5: 0 / 0 / 0.0 / 0.0 / 0; r6: 0 / 0 / 0.0 / 608.0 / 304

## Three-draw consensus (rung 0 output, mentions grouped by span overlap)
- byte-identical draws: True
- mentions 298: all agree 298 (100.0%), same span diff code 0, same code diff span 0, both differ 0, found by two 0, found by one 0
- same span all draws 100.0%; same code where all found 100.0%

## Provenance
- rerun-finer-d0: cache `/Users/wejdanbagais/Documents/repo/reliability-ladder/.claude/worktrees/reliability-ladder-b2-menu-f77617/.llm_cache.rerun-finer-d0`, git {'sha': 'c488a46', 'branch': 'claude/plan-next-sessions-docs-17c0bc', 'dirty': False, 'dirty_files': 0}, 2026-09-03T11:28:44Z → 2026-09-03T13:44:46Z
- rerun-finer-d1: cache `/Users/wejdanbagais/Documents/repo/reliability-ladder/.claude/worktrees/reliability-ladder-b2-menu-f77617/.llm_cache.rerun-finer-d1`, git {'sha': '5c9ffd2', 'branch': 'claude/plan-next-sessions-docs-17c0bc', 'dirty': False, 'dirty_files': 0}, 2026-09-03T14:32:11Z → 2026-09-03T16:48:13Z
- rerun-finer-d2: cache `/Users/wejdanbagais/Documents/repo/reliability-ladder/.claude/worktrees/reliability-ladder-b2-menu-f77617/.llm_cache.rerun-finer-d2`, git {'sha': '5c9ffd2', 'branch': 'claude/plan-next-sessions-docs-17c0bc', 'dirty': False, 'dirty_files': 0}, 2026-09-03T17:36:10Z → 2026-09-03T19:57:02Z
