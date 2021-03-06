""" molecular graph reaction identifiers

Function arguments:
    Each function takes a list of reactant graphs and a list of product graphs.
    Note that the reactant graphs *cannot* have overlapping atom keys, and
    likewise for the product graphs. Otherwise, there would be no way to
    express the bonds broken and formed between reactants.

Function return values:
    Each function returns a list of "transformations" (see graph.trans)
    describing bonds broken and formed to transform reactants into products,
    along with sort indices for putting the reactants and products in a
    standard sort order for each reaction.
"""

import itertools
import automol
from automol import par
import automol.formula
import automol.convert.graph
import automol.graph.trans as trans
from automol.graph._graph_base import string
from automol.graph._graph_base import atom_symbol_idxs
from automol.graph._graph import atom_count
from automol.graph._graph import heavy_atom_count
from automol.graph._graph import electron_count
from automol.graph._graph import atom_keys
from automol.graph._graph import bond_keys
from automol.graph._graph import standard_keys_for_sequence
from automol.graph._graph import explicit
from automol.graph._graph import without_stereo_parities
from automol.graph._graph import union
from automol.graph._graph import union_from_sequence
from automol.graph._graph import connected_components
from automol.graph._graph import full_isomorphism
from automol.graph._graph import add_bonds
from automol.graph._graph import remove_bonds
from automol.graph._graph import remove_atoms
from automol.graph._graph import add_atom_explicit_hydrogen_keys
from automol.graph._graph import unsaturated_atom_keys
from automol.graph._graph import atom_neighbor_keys
from automol.graph._res import resonance_dominant_radical_atom_keys
from automol.graph._func_group import chem_unique_atoms_of_type
from automol.graph._func_group import bonds_of_order


def is_valid_reaction(rct_gras, prd_gras):
    """ is this a valid reaction, with the same overall formula for reactants
    and products?
    """
    rct_fmls = list(map(automol.convert.graph.formula, rct_gras))
    prd_fmls = list(map(automol.convert.graph.formula, prd_gras))
    return automol.formula.reac.is_valid_reaction(rct_fmls, prd_fmls)


def is_trivial_reaction(rct_gras, prd_gras):
    """ is this a trivial reaction, with the same reactants and products?
    """
    tras, _, _ = trivial_reaction(rct_gras, prd_gras)
    return bool(tras)


def trivial_reaction(rct_gras, prd_gras):
    """ is this a trivial reaction, with the same reactants and products?
    """
    _assert_is_valid_reagent_graph_list(rct_gras)
    _assert_is_valid_reagent_graph_list(prd_gras)

    tras = []
    rct_idxs = None
    prd_idxs = None

    if len(rct_gras) == len(prd_gras):
        prd_gras = list(prd_gras)

        num = len(rct_gras)
        rct_idxs = tuple(range(num))
        prd_idxs = [0] * num

        # cycle through reactants and check for matching products
        for rct_idx, rct_gra in enumerate(rct_gras):
            prd_idx = next((idx for idx, prd_gra in enumerate(prd_gras)
                            if full_isomorphism(rct_gra, prd_gra)), None)

            # if the reactant has a matching product, remove it from the
            # products list
            if prd_idx is not None:
                prd_idxs[rct_idx] = prd_idx
                prd_gras.pop(prd_idx)
            # if the reactant has no matching product, this is not a
            # trivial reaction
            else:
                tras = []
                rct_idxs = prd_idxs = None
                break

    if rct_idxs is not None:
        tra = trans.from_data(
            rxn_class=par.REACTION_CLASS.TRIVIAL,
            frm_bnd_keys=[],
            brk_bnd_keys=[])
        tras = (tra,)
        rct_idxs = tuple(rct_idxs)
        prd_idxs = tuple(prd_idxs)

    tras = tuple(tras)

    return tras, rct_idxs, prd_idxs


def hydrogen_migration(rct_gras, prd_gras):
    """ find a hydrogen migration transformation

    Hydrogen migrations are identified by adding a hydrogen to an unsaturated
    site of the reactant and adding a hydrogen to an unsaturated site of the
    product and seeing if they match up. If so, we have a hydrogen migration
    between these two sites.
    """
    _assert_is_valid_reagent_graph_list(rct_gras)
    _assert_is_valid_reagent_graph_list(prd_gras)

    tras = []
    rct_idxs = None
    prd_idxs = None

    is_triv = is_trivial_reaction(rct_gras, prd_gras)

    if len(rct_gras) == 1 and len(prd_gras) == 1 and not is_triv:
        gra1, = rct_gras
        gra2, = prd_gras
        h_atm_key1 = max(atom_keys(gra1)) + 1
        h_atm_key2 = max(atom_keys(gra2)) + 1

        atm_keys1 = unsaturated_atom_keys(gra1)
        atm_keys2 = unsaturated_atom_keys(gra2)
        for atm_key1, atm_key2 in itertools.product(atm_keys1, atm_keys2):
            gra1_h = add_atom_explicit_hydrogen_keys(
                gra1, {atm_key1: [h_atm_key1]})
            gra2_h = add_atom_explicit_hydrogen_keys(
                gra2, {atm_key2: [h_atm_key2]})

            inv_atm_key_dct = full_isomorphism(gra2_h, gra1_h)
            if inv_atm_key_dct:
                tra = trans.from_data(
                    rxn_class=par.REACTION_CLASS.HYDROGEN_MIGRATION,
                    frm_bnd_keys=[{atm_key1,
                                   inv_atm_key_dct[h_atm_key2]}],
                    brk_bnd_keys=[{inv_atm_key_dct[atm_key2],
                                   inv_atm_key_dct[h_atm_key2]}])
                tras.append(tra)

                rct_idxs = (0,)
                prd_idxs = (0,)

    tras = tuple(tras)

    return tras, rct_idxs, prd_idxs


def hydrogen_abstraction(rct_gras, prd_gras):
    """ find a hydrogen abstraction transformation

    Hydrogen abstractions are identified first by checking whether the
    molecular formulas are consistent with a reaction of the form R1H + R2 =>
    R2H + R1. If they do, we identify the abstraction sites by adding hydrogens
    to unsaturated sites of the R1 product to see if we get the R1H reactant.
    We then do the same for the R2 reactant and the R2H product.
    """
    _assert_is_valid_reagent_graph_list(rct_gras)
    _assert_is_valid_reagent_graph_list(prd_gras)

    tras = []
    rct_idxs = None
    prd_idxs = None

    is_triv = is_trivial_reaction(rct_gras, prd_gras)

    if len(rct_gras) == 2 and len(prd_gras) == 2 and not is_triv:
        rct_fmls = list(map(automol.convert.graph.formula, rct_gras))
        prd_fmls = list(map(automol.convert.graph.formula, prd_gras))

        ret = automol.formula.reac.argsort_hydrogen_abstraction(
            rct_fmls, prd_fmls)
        if ret:
            rct_idxs_, prd_idxs_ = ret

            q1h_gra, q2_gra = list(map(rct_gras.__getitem__, rct_idxs_))
            q2h_gra, q1_gra = list(map(prd_gras.__getitem__, prd_idxs_))

            rets1 = _partial_hydrogen_abstraction(q1h_gra, q1_gra)
            rets2 = _partial_hydrogen_abstraction(q2h_gra, q2_gra)
            for ret1, ret2 in itertools.product(rets1, rets2):
                q1h_q_atm_key, q1h_h_atm_key, _ = ret1
                _, _, q2_q_atm_key = ret2

                frm_bnd_key = frozenset({q2_q_atm_key, q1h_h_atm_key})
                brk_bnd_key = frozenset({q1h_q_atm_key, q1h_h_atm_key})

                tra = trans.from_data(
                    rxn_class=par.REACTION_CLASS.HYDROGEN_ABSTRACTION,
                    frm_bnd_keys=[frm_bnd_key],
                    brk_bnd_keys=[brk_bnd_key])

                tras.append(tra)

                rct_idxs = rct_idxs_
                prd_idxs = prd_idxs_

    tras = tuple(tras)
    return tras, rct_idxs, prd_idxs


def _partial_hydrogen_abstraction(qh_gra, q_gra):
    rets = []

    h_atm_key = max(atom_keys(q_gra)) + 1
    uns_atm_keys = unsaturated_atom_keys(q_gra)
    for atm_key in uns_atm_keys:
        q_gra_h = add_atom_explicit_hydrogen_keys(
            q_gra, {atm_key: [h_atm_key]})
        inv_atm_key_dct = full_isomorphism(q_gra_h, qh_gra)
        if inv_atm_key_dct:
            qh_q_atm_key = inv_atm_key_dct[atm_key]
            qh_h_atm_key = inv_atm_key_dct[h_atm_key]
            q_q_atm_key = atm_key
            rets.append((qh_q_atm_key, qh_h_atm_key, q_q_atm_key))

    return rets


def addition(rct_gras, prd_gras):
    """ find an addition transformation

    Additions are identified by joining an unsaturated site on one reactant to
    an unsaturated site on the other. If the result matches the products, this
    is an addition reaction.
    """
    _assert_is_valid_reagent_graph_list(rct_gras)
    _assert_is_valid_reagent_graph_list(prd_gras)

    tras = []
    rct_idxs = None
    prd_idxs = None

    is_triv = is_trivial_reaction(rct_gras, prd_gras)

    if len(rct_gras) == 2 and len(prd_gras) == 1 and not is_triv:
        x_gra, y_gra = rct_gras
        prd_gra, = prd_gras
        x_atm_keys = unsaturated_atom_keys(x_gra)
        y_atm_keys = unsaturated_atom_keys(y_gra)

        for x_atm_key, y_atm_key in itertools.product(x_atm_keys, y_atm_keys):
            xy_gra = add_bonds(
                union(x_gra, y_gra), [{x_atm_key, y_atm_key}])

            atm_key_dct = full_isomorphism(xy_gra, prd_gra)
            if atm_key_dct:
                tra = trans.from_data(
                    rxn_class=par.REACTION_CLASS.ADDITION,
                    frm_bnd_keys=[{x_atm_key, y_atm_key}],
                    brk_bnd_keys=[])
                tras.append(tra)

                # sort the reactants so that the largest species is first
                rct_idxs = _argsort_reactants(rct_gras)
                prd_idxs = (0,)

    tras = tuple(tras)
    return tras, rct_idxs, prd_idxs


def beta_scission(rct_gras, prd_gras):
    """ find a beta scission transformation

    Implemented as the reverse of an addition reaction.
    """
    tras = []

    rev_tras, prd_idxs, rct_idxs = addition(prd_gras, rct_gras)
    if rev_tras:
        rct_gra = union_from_sequence(rct_gras)
        prd_gra = union_from_sequence(prd_gras)
        tras = [trans.reverse(tra, prd_gra, rct_gra) for tra in rev_tras]

    tras = tuple(set(tras))
    return tras, rct_idxs, prd_idxs


def ring_forming_scission(rct_gras, prd_gras):
    """ find a ring forming reaction that eliminates a radical group
    """
    _assert_is_valid_reagent_graph_list(rct_gras)
    _assert_is_valid_reagent_graph_list(prd_gras)

    tras = []
    rct_idxs = None
    prd_idxs = None

    is_triv = is_trivial_reaction(rct_gras, prd_gras)

    if len(rct_gras) == 1 and len(prd_gras) == 2 and not is_triv:
        rgra, = rct_gras
        pgra1, pgra2 = prd_gras
        pgra = automol.graph.union(pgra1, pgra2)
        rad_atm_keys = unsaturated_atom_keys(rgra)
        atms, bnds = rgra
        ngb_atms = automol.graph.atom_neighbor_keys(rgra)

        for rad_atm in rad_atm_keys:
            for xatm in atms:
                if (xatm != rad_atm and
                        atms[xatm][1] != 'H' and
                        xatm not in ngb_atms[rad_atm] and
                        not tras):
                    for natm in ngb_atms[xatm]:
                        if natm != rad_atm:
                            xgra = atms.copy(), bnds.copy()
                            xgra = add_bonds(
                                xgra, [frozenset({rad_atm, xatm})])
                            xgra = remove_bonds(
                                xgra, [frozenset({xatm, natm})])
                            atm_key_dct = full_isomorphism(xgra, pgra)
                            if atm_key_dct:
                                tra = trans.from_data(
                                    rxn_class=(
                                        par.REACTION_CLASS.RING_FORM_SCISSION),
                                    frm_bnd_keys=[{rad_atm, xatm}],
                                    brk_bnd_keys=[{xatm, natm}, ]
                                )
                                tras.append(tra)
                                break

                # sort the reactants so that the largest species is first
        rct_idxs = (0,)
        prd_idxs = _argsort_reactants(prd_gras)
        tras = tuple(tras)

    return tras, rct_idxs, prd_idxs


def elimination(rct_gras, prd_gras):
    """ find an elimination transformation

    Eliminations are identified by breaking two bonds from the reactant,
    forming three fragments. This will form one "central fragment" with two
    break sites and two "end fragments" with one break site each. If the
    central fragment plus the two end fragments, joined at their break sites,
    matches the products, this is an elimination reaction.
    """
    _assert_is_valid_reagent_graph_list(rct_gras)
    _assert_is_valid_reagent_graph_list(prd_gras)

    tras = []
    rct_idxs = None
    prd_idxs = None

    is_triv = is_trivial_reaction(rct_gras, prd_gras)

    if len(rct_gras) == 1 and len(prd_gras) == 2 and not is_triv:
        rct_gra, = rct_gras
        rct_bnd_keys = bond_keys(rct_gra)
        # Loop over pairs of bonds and break them. Then, if this forms three
        # fragments, join the two end fragments and compare the result to the
        # products.
        for brk_bnd_key1, brk_bnd_key2 in itertools.combinations(
                rct_bnd_keys, r=2):
            rct_gra_ = remove_bonds(rct_gra, [brk_bnd_key1, brk_bnd_key2])

            # Find the central fragment, which is the one connected to both
            # break sites. If there's a loop there may not be a central
            # fragment, in which case this function will return None.
            cent_frag_atm_keys = _central_fragment_atom_keys(
                rct_gra_, brk_bnd_key1, brk_bnd_key2)
            if cent_frag_atm_keys is not None:
                atm1_key, = brk_bnd_key1 - cent_frag_atm_keys
                atm2_key, = brk_bnd_key2 - cent_frag_atm_keys
                frm_bnd_key = frozenset({atm1_key, atm2_key})
                rct_gra_ = add_bonds(rct_gra_, [frm_bnd_key])

                prd_gra = union_from_sequence(prd_gras)
                atm_key_dct = full_isomorphism(rct_gra_, prd_gra)
                if atm_key_dct:
                    tra = trans.from_data(
                        rxn_class=par.REACTION_CLASS.ELIMINATION,
                        frm_bnd_keys=[frm_bnd_key],
                        brk_bnd_keys=[brk_bnd_key1, brk_bnd_key2])
                    tras.append(tra)

                    rct_idxs = (0,)

                    cent_prd_atm_keys = frozenset(
                        map(atm_key_dct.__getitem__, cent_frag_atm_keys))

                    if cent_prd_atm_keys <= atom_keys(prd_gras[0]):
                        prd_idxs = (0, 1)
                    else:
                        assert cent_prd_atm_keys <= atom_keys(prd_gras[1])
                        prd_idxs = (1, 0)

    tras = tuple(tras)
    return tras, rct_idxs, prd_idxs


def _central_fragment_atom_keys(gra, brk_bnd_key1, brk_bnd_key2):
    """ Determine atom keys for the central fragment after breaking two bonds.

    The central fragment is the one connected to both break sites.  If there's
    a loop there may not be a central fragment, in which case this function
    will return None.
    """
    gras = connected_components(gra)
    atm_keys = None
    if len(gras) == 3:
        for atm_keys_ in map(atom_keys, gras):
            if (len(brk_bnd_key1 - atm_keys_) == 1 and
                    len(brk_bnd_key2 - atm_keys_) == 1):
                atm_keys = atm_keys_
    return atm_keys


def insertion(rct_gras, prd_gras):
    """ find a insertion transformation

    Implemented as the reverse of an elimination transformation.
    """
    tras = []

    rev_tras, prd_idxs, rct_idxs = elimination(prd_gras, rct_gras)
    if rev_tras:
        rct_gra = union_from_sequence(rct_gras)
        prd_gra = union_from_sequence(prd_gras)
        tras = [trans.reverse(tra, prd_gra, rct_gra) for tra in rev_tras]

    tras = tuple(set(tras))
    return tras, rct_idxs, prd_idxs


def substitution(rct_gras, prd_gras):
    """ find an substitution transformation

    Substitutions are identified by breaking one bond in the reactants and one
    bond from the products and checking for isomorphism.
    """
    _assert_is_valid_reagent_graph_list(rct_gras)
    _assert_is_valid_reagent_graph_list(prd_gras)

    tras = []
    rct_idxs = None
    prd_idxs = None

    is_triv = is_trivial_reaction(rct_gras, prd_gras)

    if len(rct_gras) == 2 and len(prd_gras) == 2 and not is_triv:
        rct_gra = union_from_sequence(rct_gras)
        prd_gra = union_from_sequence(prd_gras)

        rct_bnd_keys = bond_keys(rct_gra)
        prd_bnd_keys = bond_keys(prd_gra)
        for rct_bnd_key, prd_bnd_key in itertools.product(
                rct_bnd_keys, prd_bnd_keys):
            rct_gra_ = remove_bonds(rct_gra, [rct_bnd_key])
            prd_gra_ = remove_bonds(prd_gra, [prd_bnd_key])

            inv_atm_key_dct = full_isomorphism(prd_gra_, rct_gra_)
            if inv_atm_key_dct:
                brk_bnd_key = rct_bnd_key
                frm_bnd_key = frozenset(
                    map(inv_atm_key_dct.__getitem__, prd_bnd_key))

                tra = trans.from_data(
                    rxn_class=par.REACTION_CLASS.SUBSTITUTION,
                    frm_bnd_keys=[frm_bnd_key],
                    brk_bnd_keys=[brk_bnd_key])
                tras.append(tra)

                rct_idxs = _argsort_reactants(rct_gras)
                prd_idxs = _argsort_reactants(prd_gras)

    tras = tuple(set(tras))
    return tras, rct_idxs, prd_idxs


REACTION_FINDER_DCT = {
    par.REACTION_CLASS.TRIVIAL: trivial_reaction,
    par.REACTION_CLASS.HYDROGEN_MIGRATION: hydrogen_migration,
    par.REACTION_CLASS.HYDROGEN_ABSTRACTION: hydrogen_abstraction,
    par.REACTION_CLASS.ADDITION: addition,
    par.REACTION_CLASS.BETA_SCISSION: beta_scission,
    par.REACTION_CLASS.ELIMINATION: elimination,
    par.REACTION_CLASS.INSERTION: insertion,
    par.REACTION_CLASS.SUBSTITUTION: substitution,
}


def classify_simple(rct_gras, prd_gras):
    """ classify a reaction

    (simpler call for when we don't care about the indices)
    (doesn't require explicit graphs)
    """

    # ensure that we feed explicit graphs into the classifier
    rct_gras = list(map(explicit, rct_gras))
    prd_gras = list(map(explicit, prd_gras))

    rct_gras = list(map(without_stereo_parities, rct_gras))
    prd_gras = list(map(without_stereo_parities, prd_gras))

    rct_gras, _ = standard_keys_for_sequence(rct_gras)
    prd_gras, _ = standard_keys_for_sequence(prd_gras)

    tras, _, _ = classify(rct_gras, prd_gras)

    rxn_type = None if not tras else trans.reaction_class(tras[0])

    return rxn_type


def classify(rct_gras, prd_gras):
    """ classify a reaction
    """

    # check whether this is a valid reaction
    rct_fmls = list(map(automol.formula.string,
                        map(automol.convert.graph.formula, rct_gras)))
    prd_fmls = list(map(automol.formula.string,
                        map(automol.convert.graph.formula, prd_gras)))
    assert is_valid_reaction(rct_gras, prd_gras), (
        "Invalid reaction: {:s} -> {:s}".format(str(rct_fmls), str(prd_fmls)))

    for rxn_finder in REACTION_FINDER_DCT.values():
        tras, rct_idxs, prd_idxs = rxn_finder(rct_gras, prd_gras)
        if tras:
            break

    return tras, rct_idxs, prd_idxs


REV_REACTION_FINDER_DCT = {
    par.REACTION_CLASS.HYDROGEN_MIGRATION:
    par.REACTION_CLASS.HYDROGEN_MIGRATION,
    par.REACTION_CLASS.HYDROGEN_ABSTRACTION:
    par.REACTION_CLASS.HYDROGEN_ABSTRACTION,
    par.REACTION_CLASS.ADDITION: par.REACTION_CLASS.BETA_SCISSION,
    par.REACTION_CLASS.BETA_SCISSION: par.REACTION_CLASS.ADDITION,
    # par.REACTION_CLASS.ELIMINATION: elimination,
    # par.REACTION_CLASS.INSERTION: insertion,
    # par.REACTION_CLASS.SUBSTITUTION: substitution,
}


def reverse_class(rxn_class):
    """ determine the reverse of a reaction class
    """
    return REV_REACTION_FINDER_DCT.get(rxn_class, None)


# def rxn_molecularity(rct_gras, prd_gras):
#     """ Determine molecularity of the reaction
#     """
#     rct_molecularity = len(rct_gras)
#     prd_molecularity = len(prd_gras)
#     rxn_molecularity = (rct_molecularity, prd_molecularity)
#     return rxn_molecularity


def _assert_is_valid_reagent_graph_list(gras):
    gras_str = '\n---\n'.join(map(string, gras))
    assert _are_all_explicit(gras), (
        "Implicit hydrogens are not allowed here!\nGraphs:\n{}"
        .format(gras_str))
    assert _have_no_stereo_assignments(gras), (
        "Stereo assignments are not allowed here!\nGraphs:\n{}"
        .format(gras_str))
    assert _have_no_common_atom_keys(gras), (
        "Overlapping atom keys are not allowed here!\nGraphs:\n{}"
        .format(gras_str))


def _are_all_explicit(gras):
    return all(gra == explicit(gra) for gra in gras)


def _have_no_stereo_assignments(gras):
    return all(gra == without_stereo_parities(gra) for gra in gras)


def _have_no_common_atom_keys(gras):
    atm_keys = list(itertools.chain(*map(atom_keys, gras)))
    return len(atm_keys) == len(set(atm_keys))


def _argsort_reactants(gras):

    def __sort_value(args):
        _, gra = args
        val = (-heavy_atom_count(gra),
               -atom_count(gra),
               -electron_count(gra))
        return val

    idxs = tuple(idx for idx, gra in sorted(enumerate(gras), key=__sort_value))
    return idxs


# GENERATE GRAPHS THAT ARE PRODUCTS OF CERTAIN PROCESSES
def prod_hydrogen_abstraction(x_gra, y_gra):
    """ products of hydrogen loss (generalize to group loss?)
    """

    prod_gras = tuple()

    # Build the H atom graph
    num_y_gra = len(automol.graph.atoms(y_gra)) + 1
    h_gra = ({num_y_gra: ('H', 0, None)}, {})

    # Form graphs where rct1 loses H and rct2 gains H
    x_gras_hloss = _prod_group_loss(x_gra, grp='H')
    y_gras_hadd = prod_addition(y_gra, h_gra)

    for gra1 in x_gras_hloss:
        for gra2 in y_gras_hadd:
            prod_gras += ((gra1, gra2),)

    return prod_gras


def prod_addition(x_gra, y_gra):
    """ products of addition
    """

    prod_gras = tuple()

    shift = len(automol.graph.atoms(x_gra))
    y_gra = automol.graph.transform_keys(y_gra, lambda x: x+shift)

    x_keys = unsaturated_atom_keys(x_gra)
    y_keys = unsaturated_atom_keys(y_gra)

    for x_key, y_key in itertools.product(x_keys, y_keys):
        xy_gra = add_bonds(union(x_gra, y_gra), [{x_key, y_key}])
        prod_gras += ((xy_gra,),)

    return _unique_gras(prod_gras)


def prod_hydrogen_migration(gra):
    """ products of hydrogen migration
    """

    prod_gras = tuple()

    keys = atom_keys(gra)

    num_keys = len(keys)
    if num_keys > 2:
        rad_idxs = resonance_dominant_radical_atom_keys(gra)
        uni_h_idxs = chem_unique_atoms_of_type(gra, 'H')

        h_atm_key = max(keys) + 1

        for h_idx in uni_h_idxs:
            for rad_idx in rad_idxs:
                gra2 = remove_atoms(gra, [h_idx])
                gra2_h = add_atom_explicit_hydrogen_keys(
                    gra2, {rad_idx: [h_atm_key]})
                if not full_isomorphism(gra, gra2_h):
                    prod_gras += ((gra2_h,),)

    return _unique_gras(prod_gras)


def prod_beta_scission(gra):
    """ products of beta scission
    """

    prod_gras = tuple()

    rad_idxs = resonance_dominant_radical_atom_keys(gra)
    single_bonds = bonds_of_order(gra, mbond=1)

    for rad_idx in rad_idxs:
        rad_neighs = atom_neighbor_keys(gra)[rad_idx]
        for single_bond in single_bonds:
            bond = frozenset(single_bond)
            if rad_neighs & bond and rad_idx not in bond:
                gra2 = remove_bonds(gra, [bond])
                disconn_gras = automol.graph.connected_components(gra2)
                prod_gras += (disconn_gras,)

    return _unique_gras(prod_gras)


def prod_homolytic_scission(gra):
    """ products of homolytic single bond scission
    """

    prod_gras = tuple()

    single_bonds = bonds_of_order(gra, mbond=1)
    for bond in single_bonds:
        gra2 = remove_bonds(gra, [frozenset(bond)])
        disconn_gras = automol.graph.connected_components(gra2)
        prod_gras += (disconn_gras,)

    return _unique_gras(prod_gras)


def _prod_group_loss(gra, grp='H'):
    """ products of hydrogen loss. Need to generalize to group loss
    """

    prod_gras = tuple()

    symb_idx_dct = atom_symbol_idxs(gra)
    h_idxs = symb_idx_dct[grp]

    for idx in h_idxs:
        prod_gras += (remove_atoms(gra, [idx]),)

    return _unique_gras(prod_gras)


def _unique_gras(gra_lst):
    """ Determine all of the unique gras deals with gras with multiple components
    """

    uni_gras = tuple()
    if gra_lst:

        # Initialize list with first element
        uni_gras += (gra_lst[0],)

        # Test if the del_gra is isomorphic to any of the uni_del_gras
        for gra in gra_lst[1:]:
            new_uni = True
            for uni_gra in uni_gras:
                if len(gra) == 1:
                    isodct = full_isomorphism(gra, uni_gra)
                else:
                    isodct = full_isomorphism(union(*gra), union(*uni_gra))
                if isodct:
                    new_uni = False
                    break

            # Add graph and idx to lst if del gra is unique
            if new_uni:
                uni_gras += (gra,)

    return uni_gras


if __name__ == '__main__':
    # import sys
    RXNS = list(
        map(eval, open('reactions_from_luna.txt').read().splitlines()))
    for RXN in RXNS:
        RCT_ICHS, PRD_ICHS = RXN
        RCT_GRAS = list(map(automol.inchi.graph, RCT_ICHS))
        PRD_GRAS = list(map(automol.inchi.graph, PRD_ICHS))
        try:
            RXN_TYPE = classify_simple(RCT_GRAS, PRD_GRAS)
        except AssertionError as e:
            print(e)
            pass
        print(RXN_TYPE)
        if RXN_TYPE is None:
            print([RCT_ICHS, PRD_ICHS])
