import math
import mthree
import random

from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator
from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
from qiskit_ibm_runtime import SamplerV2 as Sampler, QiskitRuntimeService, IBMBackend
from typing import Dict, List

# QuantumRandomNumberGenerator
# This class generates random numbers using quantum circuits with Qiskit.
# It can apply error mitigation for higher fidelity results.
# The class requires an IBMQ token to access IBM's quantum resources.

class QuantumRandomNumberGenerator:
    def __init__(self,num_possible_outcomes,api_token='YOUR-IBMQ-TOKEN',backend="ibm_sherbrooke") -> None:
        """
        Initialize the QuantumRandomNumberGenerator.
    
        Parameters:
        num_possible_outcomes (int): Number of possible outcomes for random numbers.
        api_token (str): IBMQ token for accessing the quantum backends.
        backend (str): Backend name to use for the Aer simulator and noise model.
        """
        self.num_possible_outcomes = num_possible_outcomes
        self.num_qubits = math.ceil(math.log2(self.num_possible_outcomes)) # `num_qubits` calculates the minimum number of qubits required to represent all possible outcomes.
        self.api_token = api_token
        self.max_number_bin = format(self.num_possible_outcomes, f'0{self.num_qubits}b')
        
        # Attempt to initialize QiskitRuntimeService; will prompt for API setup if unsuccessful
        try:
            self.service = QiskitRuntimeService()
        except Exception:
            try:
                self._log_into_qiskit_runtime()
            except Exception:
                print("Please configure your IBMQ token. You can obtain it by signing up at quantum.ibm.com")
            
        # Backend setup: `real_backend` is used for noise modeling, mapped to Aer simulator as `aer`
        real_backend = self.service.backend(backend)
        aer = AerSimulator.from_backend(real_backend)
        
        # Initialize the Sampler and M3Mitigation instances, which will manage circuit sampling and measurement error mitigation
        self.sampler = Sampler(mode=aer)
        self.mit = mthree.M3Mitigation(aer)
        
        self.single_circuit = False
        
        # Determines if a single circuit will be used (if `num_qubits` <= 10) or if the circuit must be divided
        if self.num_qubits <= 10:
            
            self.single_circuit = True
            
            # Prepare the main quantum circuit with `num_qubits` or 10 qubits as needed
            qc = QuantumCircuit(self.num_qubits)
            
            # Add a Hadamard gates to all qubits and measure
            for qubit in range(self.num_qubits):
                qc.h(qubit)
            qc.measure_all()
            
            self.main_correction_permutations = 2**self.num_qubits
            
            # Initialize pass manager with aer backend
            self.pm = generate_preset_pass_manager(backend=aer, optimization_level=1)
            
            # Transpile the circuit to the corresponding backend
            self.transpiled_qc = self.pm.run(qc)

            # Map measurements for error mitigation, linking qubit measurement positions
            self.qc_mapping = mthree.utils.final_measurement_mapping(self.transpiled_qc)

        else:
            # Divide the circuit if we need more than 10 qubits
            # If remainder is greater than zero, we generate an additional circuit with that number of qubits
            self.quotient, remainder = divmod(self.num_qubits, 10)
            # We will run the same 10 qubit circuit 'quotient' times
            
            # Create a single circuit with 10 qubits
            qc = QuantumCircuit(10)
            
            # Add a Hadamard gates to all qubits and measure
            for qubit in range(10):
                qc.h(qubit)
            qc.measure_all()
            
            self.main_correction_permutations = 1024 # == 2**10
            
            # Initialize pass manager with aer backend
            self.pm = generate_preset_pass_manager(backend=aer, optimization_level=1)
            
            # Transpile the circuit to the corresponding backend
            self.transpiled_qc = self.pm.run(qc)

            # Pass the transpiled circuit for mapping to the M3 requirements
            self.qc_mapping = mthree.utils.final_measurement_mapping(self.transpiled_qc)
            
            self.remainder_circuits= False
            
            if remainder > 0:
                
                self.remainder_circuits = True
                
                # Create a new circuit with remainder qubits
                rem_qc = QuantumCircuit(remainder)
                # Add a Hadamard gates to all qubits and measure
                for qubit in range(remainder):
                    rem_qc.h(qubit)
                rem_qc.measure_all()
                
                # Transpile the circuit to the corresponding backend
                self.transpiled_rem_qc = self.pm.run(rem_qc)
                
                # Pass the transpiled circuit for mapping to the M3 requirements
                self.rem_qc_mapping = mthree.utils.final_measurement_mapping(self.transpiled_rem_qc)
                
                self.rem_correction_permutations = 2**remainder


    def _log_into_qiskit_runtime(self) -> None:
        """
        Logs into QiskitRuntimeService using the provided IBMQ token,
        which is necessary for accessing IBMQ backends.
        """
        QiskitRuntimeService.save_account(channel="ibm_quantum", token=self.api_token, overwrite=True)

    def available_backends(self) -> List[IBMBackend]:
        """
        Retrieve available QPUs to the user's IBMQ account.
        
        Returns:
            List of IBMBackend instances available for the user's account.
        """
        available = self.service.backends()
        return available

    def _run_and_correct(self, main_qc = None, rem_qc = None, num_shots=1024) -> mthree.classes.QuasiDistribution:
        """
        Run the circuit on the Aer simulator and apply M3 error mitigation corrections
        If `main_qc` is True, runs the main quantum circuit; otherwise, the remainder circuit (if available)        
        Parameters:
            main_qc (bool): Whether to run the main quantum circuit.
            rem_qc (bool): Whether to run the remainder circuit.
            num_shots (int): Number of shots for the circuit execution.
        Returns:
            Quasi-distribution with error-mitigated counts.
        """
        if main_qc is not None:
            transpiled_qc = self.transpiled_qc
            mapping = self.qc_mapping
            self.mit.cals_from_system(mapping) # Perform error mitigation calibration based on the mapping
            
        elif rem_qc is not None:
            transpiled_qc = self.transpiled_rem_qc
            mapping = self.rem_qc_mapping
            self.mit.cals_from_system(mapping) # Perform error mitigation calibration based on the mapping
        
        result = self.sampler.run([transpiled_qc],shots=num_shots).result()
        
        # Obtain raw counts and apply error mitigation to get quasi-probability distribution
        counts = result[0].data.meas.get_counts()
        quasis = self.mit.apply_correction(counts,mapping)
        
        return quasis
    
    def _gen_flattened_quasis_dict(self, main_qc: bool = None, rem_qc: bool = None, mitigation_level: float = 1 ) -> Dict:
        """
        Generate and return a dictionary with quasi-probabilities obtained from multiple circuit runs,
        applying randomized error mitigation via permuting the quasi-probabilities.

        This function runs a series of quantum circuits (either the main circuit or remainder circuit, or both),
        collects the resulting quasi-probabilities, applies random permutations for error mitigation, and 
        accumulates the permuted values across multiple iterations. The final result is a dictionary containing
        the summed quasi-probabilities across all iterations.

        Parameters:
            main_qc (bool): 
                If True, the main quantum circuit will be executed.
                
            rem_qc (bool): 
                If True, the remainder circuit will be executed.
            
            mitigation_level (float): 
                A float between 0 and 1 (inclusive), specifying the fraction of total permutations to run.
                A value of 1 means the maximum number of permutations will be applied; a value closer to 0 
                will apply fewer permutations (but still greater than 0). Default is 1.

        Returns:
            Dict:
                A dictionary where keys represent the possible outcomes of the quantum circuit,
                and values are the summed quasi-probabilities from all iterations. Each key in the dictionary 
                corresponds to a unique outcome, and the values represent the accumulated quasi-probabilities 
                after applying random permutations across multiple correction iterations.
        
        Raises:
            ValueError:
                If the provided mitigation_level is not within the valid range (0, 1].

        Example:
            _gen_flattened_quasis_dict(main_qc=True, rem_qc=False, mitigation_level=0.8)
                Returns a dictionary of summed quasi-probabilities after running 80% of the total correction permutations
                using the main quantum circuit, with error mitigation applied via random permutations.
        """
        
        # Validate the mitigation level to ensure it is within the range (0, 1]
        if not (0 < mitigation_level <= 1):
            raise ValueError("Mitigation level must be within (0,1] interval.")
        
        # Determine the number of permutations to apply based on the mitigation level and circuit selection
        if main_qc is not None:
            iterations = math.ceil(mitigation_level*self.main_correction_permutations)
            
        elif rem_qc is not None:
            iterations = math.ceil(mitigation_level*self.rem_correction_permutations)
        
        corrected_counts = [] # Initialize an empty list to store corrected quasi-probabilities
        
        # Perform the specified number of permutations
        for _ in range(iterations):
            quasis = self._run_and_correct(main_qc = main_qc, rem_qc = rem_qc) # Run the circuit and perform M3 mitigation
            values = list(quasis.values()) # Extract the quasi-probabilities (values) from the dictionary
            
            # Randomly permute quasi-probabilities on each iteration for unbiased error mitigation
            random.shuffle(values) # Shuffle the quasi-probabilities to simulate error mitigation
            
            # Recreate the quasi-probabilities dictionary with permuted values
            permuted_quasis = dict(zip(quasis.keys(), values))
            corrected_counts.append(permuted_quasis) # Append the permuted dictionary to the list of corrected counts
            
        flattened_counts = {key: 0 for key in corrected_counts[0].keys()} # Initialize an empty dictionary to store the sums

        # Sum the quasi-probabilities across all iterations for each possible outcome
        for counts in corrected_counts:
            for key, value in counts.items():
                flattened_counts[key] += value # Summing across iterations for each possible outcome
        
        # Return the accumulated, flattened quasi-probabilities
        return flattened_counts
    
    def _select_number(self, counts: Dict) -> str:
        """
        Choose the outcome with the highest quasi-probability count within the allowed range.
        This approach ensures a valid outcome within `num_possible_outcomes`.
        Parameters:
            counts (Dict): Corrected counts of measured outcomes.
        
        Returns:
            Binary string representing the selected outcome.
        """
        # Filter the dictionary to keep only items where the key is less than or equal to the comparison key
        filtered_counts = {k: v for k, v in counts.items() if k <= self.max_number_bin}
        
        max_key = max(filtered_counts, key=filtered_counts.get) # Find the key with the maximum value
        
        return max_key

    def _merge_counts(self, *all_counts) -> Dict:
        """
        Merging multiple quasi-distribution counts from different circuit runs
        Concatenates binary keys from each count dict, combining results from multiple runs

        Parameters:
            all_counts: Sequence of dictionaries with quasi-distribution counts.
            
        Returns:
            Merged dictionary with concatenated keys and multiplied values.
        """
        merged_counts = all_counts[0] # Start with the first dictionary in all_counts

        # Iterate through the remaining dictionaries
        for next_dict in all_counts[1:]:
            new_merged_counts = {} # Initialize an empty dictionary to hold the new merged counts

            # Perform pairwise merging of `merged_counts` and `next_dict`
            for key1, value1 in merged_counts.items():
                for key2, value2 in next_dict.items():
                    combined_key = key1 + key2  # Concatenate keys to form a longer key
                    new_merged_counts[combined_key] = value1 * value2   # Multiply quasi-probabilities
                    
            # Update merged_counts with the new merged result
            merged_counts = new_merged_counts

        # Return the fully merged dictionary
        return merged_counts
        
    def fast_random_number(self) -> int:
        """
        Generate a random number faster by skipping gate error mitigation
        
        Returns:
            Random integer based on the quantum sampling output.
        """
        if self.single_circuit:
            result = self._select_number(self._run_and_correct(main_qc=True))
        else:
            results = []
            for _ in range(self.quotient):
                results.append(self._run_and_correct(main_qc=True))
            if self.remainder_circuits:
                results.append(self._run_and_correct(rem_qc=True))
            result = self._select_number(self._merge_counts(*results))
        return int(result,2)
        
    def gate_error_mit_random_number(self, mitigation_level = 1) -> int:
        """
        Generate a random number with gate error mitigation applied.
        
        Returns:
            Random integer with error-mitigated quasi-probability values.
        """
        if self.single_circuit:
            result = self._select_number(self._gen_flattened_quasis_dict(main_qc=True,mitigation_level=mitigation_level))
        else:
            results = []
            for _ in range(self.quotient):
                results.append(self._gen_flattened_quasis_dict(main_qc=True,mitigation_level=mitigation_level))
            if self.remainder_circuits:
                results.append(self._gen_flattened_quasis_dict(rem_qc=True,mitigation_level=mitigation_level))
            result = self._select_number(self._merge_counts(*results))
        return int(result,2)