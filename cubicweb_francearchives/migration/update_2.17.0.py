# -*- coding: utf-8 -*-
#
# flake8: noqa
# Copyright © LOGILAB S.A. (Paris, FRANCE) 2016-2021
# Contact http://www.logilab.fr -- mailto:contact@logilab.fr
#
# This software is governed by the CeCILL-C license under French law and
# abiding by the rules of distribution of free software. You can use,
# modify and/ or redistribute the software under the terms of the CeCILL-C
# license as circulated by CEA, CNRS and INRIA at the following URL
# "http://www.cecill.info".
#
# As a counterpart to the access to the source code and rights to copy,
# modify and redistribute granted by the license, users are provided only
# with a limited warranty and the software's author, the holder of the
# economic rights, and the successive licensors have only limited liability.
#
# In this respect, the user's attention is drawn to the risks associated
# with loading, using, modifying and/or developing or reproducing the
# software by the user in light of its specific status of free software,
# that may mean that it is complicated to manipulate, and that also
# therefore means that it is reserved for developers and experienced
# professionals having in-depth computer knowledge. Users are therefore
# encouraged to load and test the software's suitability as regards their
# requirements in conditions enabling the security of their systemsand/or
# data to be ensured and, more generally, to use and operate it in the
# same conditions as regards security.
#
# The fact that you are presently reading this means that you have had
# knowledge of the CeCILL-C license and that you accept its terms.

import logging

logger = logging.getLogger("francearchives.migration")

logger.info("-> qualify existing AgentAuthority")

# cf https://extranet.logilab.fr/ticket/74057619
# qualify aligned and  SubjectAuthorities and AgentAuthorities with documents
# qualify aligned and grouping LocationAuthorities

# takes > 2 mins

with cnx.allow_all_hooks_but("es", "sync", "varnish", "reindex-suggest-es"):
    rql(
        """SET A quality True WHERE A is AgentAuthority,
        EXISTS(S same_as A), EXISTS(I authority A)"""
    )
    cnx.commit()
    rql(
        """SET A quality True WHERE A is AgentAuthority,
        EXISTS(A same_as S), EXISTS(I authority A)"""
    )
    cnx.commit()
    rql(
        """SET A quality True WHERE A is AgentAuthority,
        EXISTS(S same_as A), EXISTS(I related_authority A)"""
    )
    cnx.commit()
    rql(
        """SET A quality True WHERE A is AgentAuthority,
        EXISTS(A same_as S), EXISTS(I related_authority A)"""
    )
    cnx.commit()

logger.info("-> qualify existing SubjectAuthority")

with cnx.allow_all_hooks_but("es", "sync", "varnish", "reindex-suggest-es"):
    rql(
        """SET A quality True WHERE A is SubjectAuthority,
        EXISTS(S same_as A), EXISTS(I authority A)"""
    )
    cnx.commit()
    rql(
        """SET A quality True WHERE A is SubjectAuthority,
        EXISTS(A same_as S), EXISTS(I authority A)"""
    )
    cnx.commit()
    rql(
        """SET A quality True WHERE A is SubjectAuthority,
        EXISTS(S same_as A), EXISTS(I related_authority A)"""
    )
    cnx.commit()
    rql(
        """SET A quality True WHERE A is SubjectAuthority,
        EXISTS(A same_as S), EXISTS(I related_authority A)"""
    )
    cnx.commit()

logger.info("-> qualify existing LocationAuthority")

with cnx.allow_all_hooks_but("es", "sync", "varnish", "reindex-suggest-es"):
    rql(
        """SET A quality True WHERE A is LocationAuthority, EXISTS(S same_as A, A1 grouped_with A)"""
    )
    cnx.commit()
    rql(
        """SET A quality True WHERE A is LocationAuthority, EXISTS(A same_as S, A1 grouped_with A)"""
    )
    cnx.commit()

logger.info("-> check qualifications")

for query in (
    "Any COUNT(X) WHERE X is LocationAuthority, X quality True",
    "Any COUNT(X) WHERE X is SubjectAuthority, X quality True",
    "Any COUNT(X) WHERE X is AgentAuthority, X quality True",
):
    count = rql(query)[0][0]
    print(count)
    logger.info(query, count)

for query in (
    "Any COUNT(X) WHERE X is AgentAuthority, X quality False, (X same_as A OR A same_as X), I authority X",
    "Any COUNT(X) WHERE X is AgentAuthority, X quality False, (X same_as A OR A same_as X), C related_authority X",
    "Any COUNT(X) WHERE X is SubjectAuthority, X quality False, (X same_as A OR A same_as X), I authority X",
    "Any COUNT(X) WHERE X is SubjectAuthority, X quality False, (X same_as A OR A same_as X), C related_authority X",
    "Any COUNT(X) WHERE X is LocationAuthority, X quality True, NOT A same_as X, NOT X1 grouped_with X",
    "Any COUNT(X) WHERE X is LocationAuthority, X quality False, (X same_as A OR A same_as X), X1 grouped_with X",
    "Any COUNT(X) WHERE X is LocationAuthority, X quality True, NOT X same_as A, NOT X1 grouped_with X",
):
    count = rql(query)[0][0]
    if count != 0:
        logger.info(query, count)
    assert count == 0
